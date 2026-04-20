from typing import Any, Callable, Collection
from typing_extensions import Literal

import llvmlite.ir as ir
import llvmlite.binding as llvm

if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    import constants
    from definitions import builtin_definition, unary_apply, binary_apply, multi_apply, pwarning, CompileError

llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

CompileConstruct = Literal['__MODULE__', '__IMPORT_PATH__', '__BUILDER__']
CompileConstructType = ir.Module | ir.IRBuilder | str

def _define_print_integer(module):
    # Add the declaration of printf to the module
    printf_ty = ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))], var_arg=True)
    printf = ir.Function(module, printf_ty, name="printf")

    # Create a global string for the format specifier
    fmt_str = "%d\n\0"
    fmt_str_global = ir.GlobalVariable(module, ir.ArrayType(ir.IntType(8), len(fmt_str)), name="fmt_str")
    fmt_str_global.linkage = 'internal'
    fmt_str_global.global_constant = True
    fmt_str_global.initializer = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt_str)), bytearray(fmt_str.encode("utf8"))) # type: ignore

    # Define the print_integer function (returns its argument after printing it)
    print_integer_ty = ir.FunctionType(ir.IntType(64), [ir.IntType(64)])
    print_integer = ir.Function(module, print_integer_ty, name="print_integer")
    block = print_integer.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    fmt_arg = builder.bitcast(fmt_str_global, ir.PointerType(ir.IntType(8)))
    builder.call(printf, [fmt_arg, print_integer.args[0]])
    builder.ret(print_integer.args[0])
    
def _define_print_string(module):
    # Add the declaration of puts to the module
    puts_ty = ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))])
    puts = ir.Function(module, puts_ty, name="puts")

def get_compile_construct(scope: Scope, name: CompileConstruct) -> Any: # CompileConstructType
    module_expr = scope.force_var_lookup(name)
    module_compile_prop = module_expr.force_get_property('compile')
    return module_compile_prop.associated_value

def set_compile_construct(anchor: Token, scope: Scope, name: CompileConstruct, value: CompileConstructType):
    scope.local_vars[name] = Expression(
        symbol=anchor.create_renamed(name),
        properties=[Property(anchor.create_renamed('compile'), is_association=True, associated_value=value)]
    )

def compile_last_property(expr: Expression, scope: Scope) -> Expression:
    from main import resolve_property_on
    compiled_expr = resolve_property_on(expr, Property(expr.symbol.create_renamed('compile')), scope)
    return compiled_expr

def expression_compile_all(expr: Expression, scope: Scope) -> Expression:
    '''
    Compiles all properties marked for resolution in expr.
    '''
    from main import expression_resolve_all
    expr_copy = Expression(expr.symbol, [])
    for prop in expr.properties:
        if prop.is_compound:
            prop = prop.copy()
            prop.compound_properties = [expression_resolve_all(p, scope, constants.immediate_resolve) for p in prop.compound_properties]

        if prop.property.s in constants.resolve:
            expr_copy = compile_last_property(expr_copy, scope)
            expr_copy = Expression(expr_copy.symbol, expr_copy.properties.copy())
            assert not any(p.property.s in constants.resolve for p in expr_copy.properties)
        else:
            expr_copy.properties.append(prop)
    return expr_copy


def get_compiled(expr: Expression, scope: Scope) -> ir.Value:
    compile_prop = expr.try_get_property('compile')
    if compile_prop is None:
        # There are a few literal special cases that we want to compile without resolve
        # These are integers and strings
        if (int_prop := expr.try_get_property('integer')) is not None:
            return ir.Constant(ir.IntType(64), int_prop.associated_value or 0)
        elif (str_prop := expr.try_get_property('string')) is not None:
            return CompileStringDefinition.create_string(str_prop.associated_value, scope)
        raise CompileError(f"expression {expr} is not compiled", anchor=expr.symbol)
    return compile_prop.associated_value

# Builtin types

@builtin_definition
class CompileIntegerDefinition(Definition):
    symbol = 'compile'
    property_names = ['integer']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        # TODO compile to an actual binary instead of just evaluating the expression
        ival = lhs.force_get_property('integer')
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True)
        compile_prop.associated_value = ir.Constant(ir.IntType(64), ival.associated_value or 0)
        return lhs.create_with_property(compile_prop)
    
@builtin_definition
class CompileStringDefinition(Definition):
    symbol = 'compile'
    property_names = ['string']
    # We map each (__IMPORT_PATH__, string) pair to the compiled result of the string, so that we can reuse the compiled result if the same string is compiled again in the same file
    compiled_cache: dict[tuple[str, str], ir.Value] = {}

    @classmethod
    def create_string(cls, str_val: str, scope: Scope) -> ir.Value:
        file_str = get_compile_construct(scope, '__IMPORT_PATH__')
        cache_key = (file_str, str_val)
        if cache_key in CompileStringDefinition.compiled_cache:
            return CompileStringDefinition.compiled_cache[cache_key]
        
        shared_str = ir.GlobalVariable(
            get_compile_construct(scope, '__MODULE__'), 
            ir.ArrayType(ir.IntType(8), len(str_val) + 1), 
            name=f'str_{len(CompileStringDefinition.compiled_cache)}'
        )
        shared_str.linkage = 'internal'
        shared_str.global_constant = True
        shared_str.initializer = ir.Constant(ir.ArrayType(ir.IntType(8), len(str_val) + 1), bytearray((str_val + '\0').encode("utf8"))) # type: ignore
        CompileStringDefinition.compiled_cache[cache_key] = shared_str
        return shared_str

    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        shared_str = CompileStringDefinition.create_string(lhs.force_get_property('string').associated_value, scope)
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=shared_str)
        return lhs.create_with_property(compile_prop)

# Operations on built-in types

class CompileBuiltinBinaryDefinition(Definition):
    symbol = 'compile'
    property_names: list[str]  # defined in subclasses, the last property name is the operator
    op_name: str    # the callback that generates the IR for this operation
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        property_name = self.property_names[-1]
        lhs, prop = lhs.discard_properties_after(property_name)
        builder = get_compile_construct(scope, '__BUILDER__')
        lhs_val = get_compiled(lhs, scope)
        if len(prop.compound_properties) == 0:
            raise CompileError(f"property {property_name} requires an argument, got none")
        for p in prop.compound_properties:
            rhs_expr = expression_compile_all(p, scope)
        rhs_val = get_compiled(rhs_expr, scope)
        res = getattr(builder, self.op_name)(lhs_val, rhs_val, f'{self.op_name}_tmp')
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res)
        return lhs.replace_property('compile', compile_prop)

class CompileBuiltinCompareDefinition(CompileBuiltinBinaryDefinition):
    cmp_type: str  # defined in subclasses, e.g. '==', '<', etc.
    def callback(self, builder: ir.IRBuilder, lhs_val: ir.Value, rhs_val: ir.Value, property_name: str) -> Any:
        cmp_res = builder.icmp_signed(self.cmp_type, lhs_val, rhs_val, property_name)
        ires = builder.zext(cmp_res, ir.IntType(64), property_name)
        return ires

@builtin_definition
class CompileIntegerAddDefinition(CompileBuiltinBinaryDefinition):
    property_names = ['integer', '+']
    op_name = "add"

@builtin_definition
class CompileIntegerSubtractDefinition(CompileBuiltinBinaryDefinition):
    property_names = ['integer', '-']
    op_name = "sub"

@builtin_definition
class CompileIntegerMultiplyDefinition(CompileBuiltinBinaryDefinition):
    property_names = ['integer', '*']
    op_name = "mul"

@builtin_definition
class CompileIntegerDivideDefinition(CompileBuiltinBinaryDefinition):
    property_names = ['integer', '/']
    op_name = "sdiv"

@builtin_definition
class CompileIntegerEqualDefinition(CompileBuiltinCompareDefinition):
    property_names = ['integer', '==']
    cmp_type = '=='

@builtin_definition
class CompileIntegerNotEqualDefinition(CompileBuiltinCompareDefinition):
    property_names = ['integer', '!=']
    cmp_type = '!='

@builtin_definition
class CompileIntegerLessThanDefinition(CompileBuiltinCompareDefinition):
    property_names = ['integer', '<']
    cmp_type = '<'

@builtin_definition
class CompileIntegerGreaterThanDefinition(CompileBuiltinCompareDefinition):
    property_names = ['integer', '>']
    cmp_type = '>'

@builtin_definition
class CompileIntegerLessEqualDefinition(CompileBuiltinCompareDefinition):
    property_names = ['integer', '<=']
    cmp_type = '<='

@builtin_definition
class CompileIntegerGreaterEqualDefinition(CompileBuiltinCompareDefinition):
    property_names = ['integer', '>=']
    cmp_type = '>='

@builtin_definition
class CompileIntegerLogicalNotDefinition(Definition):
    symbol = 'compile'
    property_names = ['integer', 'logical_not']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, _ = lhs.discard_properties_after('logical_not')
        builder = get_compile_construct(scope, '__BUILDER__')
        lhs_val = get_compiled(lhs, scope)
        zero = ir.Constant(ir.IntType(64), 0)
        cmp_res = builder.icmp_signed('!=', lhs_val, zero, 'logical_not_tmp')
        ires = builder.zext(cmp_res, ir.IntType(64), 'bool_to_int_tmp')
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=ires)
        return lhs.replace_property('compile', compile_prop)

# Printing

@builtin_definition
class CompilePrintIntegerDefinition(Definition):
    symbol = 'compile'
    property_names = ['integer', 'print']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, _ = lhs.discard_properties_after('print')
        builder = get_compile_construct(scope, '__BUILDER__')
        lhs_val = get_compiled(lhs, scope)
        print_res = builder.call(get_compile_construct(scope, '__MODULE__').get_global('print_integer'), [lhs_val], 'print_tmp')
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=lhs_val)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompilePrintStringDefinition(Definition):
    symbol = 'compile'
    property_names = ['string', 'print']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, _ = lhs.discard_properties_after('print')
        builder = get_compile_construct(scope, '__BUILDER__')
        lhs_val = get_compiled(lhs, scope)
        puts = get_compile_construct(scope, '__MODULE__').get_global('puts')
        str_arg = builder.bitcast(lhs_val, ir.PointerType(ir.IntType(8)))
        print_res = builder.call(puts, [str_arg], 'print_tmp')
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=lhs_val)
        return lhs.replace_property('compile', compile_prop)

# Variables

@builtin_definition
class CompileIdentifierDefinition(Definition):
    symbol = 'compile'
    property_names = ['identifier']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        var_expr = scope.var_lookup(lhs.symbol.s)
        if var_expr is None:
            # Create a global variable if it doesn't exist
            var = ir.GlobalVariable(get_compile_construct(scope, '__MODULE__'), ir.IntType(64), name=lhs.symbol.s)
            var.linkage = 'internal'
            compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=var)
            res = scope.local_vars[lhs.symbol.s] = lhs.create_with_property(compile_prop)
            return res
        else:
            # Add the property to the existing variable expression if it exists
            var = var_expr.force_get_property('compile').associated_value
            compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=var)
            return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompileDeclareDefinition(Definition):
    symbol = 'compile'
    property_names = ['declare']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        # TODO allow non-integer types
        if not any(prop.property.s == 'integer' for prop in lhs.properties):
            raise CompileError('non-integer variables not implemented yet')
        var = ir.GlobalVariable(get_compile_construct(scope, '__MODULE__'), ir.IntType(64), name=lhs.symbol.s)
        var.linkage = 'internal'
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=var)
        res = scope.local_vars[lhs.symbol.s] = lhs.create_with_property(compile_prop)
        return res
    
@builtin_definition
class CompileAssignDefinition(Definition):
    symbol = 'compile'
    property_names = ['assign']
    param_names = ['rhs']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        var_expr = scope.var_lookup(lhs.symbol.s)
        if var_expr is None:
            raise CompileError(f"variable {lhs.symbol.s} not declared")
        var = get_compiled(var_expr, scope)
        rhs_val = get_compiled(rhs, scope)
        builder = get_compile_construct(scope, '__BUILDER__')
        compile_res = builder.store(rhs_val, var)
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=compile_res)
        return lhs.replace_property('compile', compile_prop)

# Conditionals

@builtin_definition
class CompileThenDefinition(Definition):
    symbol = 'compile'
    property_names = ['then']   # This is only the 'then' block, there will be no else following
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        cond_expr, body_prop = lhs.discard_properties_after('then')
        cond_val = get_compiled(cond_expr, scope)
        builder = get_compile_construct(scope, '__BUILDER__')

        # 1. Branch: if cond != 0 goto then_block else goto merge_block
        entry_block = builder.block
        then_block = builder.append_basic_block('then') # This gets redefined later
        merge_block = builder.append_basic_block('ifcont')
        builder.cbranch(
            builder.icmp_signed('!=', cond_val, ir.Constant(ir.IntType(64), 0), 'ifcond'), 
            then_block, merge_block
        )

        # 2. Emit "Then" Block
        builder.position_at_start(then_block)
        if len(body_prop.compound_properties) == 0:
            raise CompileError('`then` block cannot be empty')
        for expr in body_prop.compound_properties:
            body_expr = expression_compile_all(expr, scope)
        body_val = get_compiled(body_expr, scope)
        builder.branch(merge_block) # go back to the main flow
        # Update then_block reference in case get_compiled created new blocks
        then_block = builder.block

        # 3. Emit Merge Block and PHI
        builder.position_at_start(merge_block)
        phi = builder.phi(ir.IntType(64), 'iftmp')
        phi.add_incoming(cond_val, entry_block) # If we came from entry, result is the 0 (cond_val)
        phi.add_incoming(body_val, then_block)  # If we came from then_block, result is the body_val
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=phi)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompileElseDefinition(Definition):
    symbol = 'compile'
    property_names = ['else']   # This is only the 'else' block, there is no then block before this
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        cond_expr, body_prop = lhs.discard_properties_after('else')
        cond_val = get_compiled(cond_expr, scope)
        builder = get_compile_construct(scope, '__BUILDER__')
        # 1. Branch: if cond != 0 goto then_block else goto merge_block
        entry_block = builder.block
        else_block = builder.append_basic_block('else') # This gets redefined later
        merge_block = builder.append_basic_block('ifcont')
        builder.cbranch(
            builder.icmp_signed('!=', cond_val, ir.Constant(ir.IntType(64), 0), 'ifcond'), 
            merge_block, else_block, 
        )

        # 2. Emit "Else" Block
        builder.position_at_start(else_block)
        if len(body_prop.compound_properties) == 0:
            raise CompileError('`else` block cannot be empty')
        for expr in body_prop.compound_properties:
            body_expr = expression_compile_all(expr, scope)
        body_val = get_compiled(body_expr, scope)
        builder.branch(merge_block) # go back to the main flow
        # Update else_block reference in case get_compiled created new blocks
        else_block = builder.block

        # 3. Emit Merge Block and PHI
        builder.position_at_start(merge_block)
        phi = builder.phi(ir.IntType(64), 'iftmp')
        phi.add_incoming(cond_val, entry_block) # If we came from entry, result is the cond_val
        phi.add_incoming(body_val, else_block)  # If we came from else_block, result is the body_val
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=phi)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompileThenElseDefinition(Definition):
    symbol = 'compile'
    property_names = ['then', 'else']   # This is the 'x then(a) else(b)' block
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, else_body_prop = lhs.discard_properties_after('else')
        cond_expr, then_body_prop = lhs.discard_properties_after('then')

        cond_val = get_compiled(cond_expr, scope)
        builder = get_compile_construct(scope, '__BUILDER__')
        # 1. Branch: if cond != 0 goto then_block else goto merge_block
        entry_block = builder.block
        then_block = builder.append_basic_block('then')
        else_block = builder.append_basic_block('else')
        merge_block = builder.append_basic_block('ifcont')
        builder.cbranch(
            builder.icmp_signed('!=', cond_val, ir.Constant(ir.IntType(64), 0), 'ifcond'), 
            then_block, else_block, 
        )

        # 2. Emit "Then" and "Else" Blocks
        builder.position_at_start(then_block)
        if len(then_body_prop.compound_properties) == 0:
            raise CompileError('`then` block cannot be empty')
        for expr in then_body_prop.compound_properties:
            then_expr = expression_compile_all(expr, scope)
        then_val = get_compiled(then_expr, scope)
        builder.branch(merge_block) # go back to the main flow
        then_block = builder.block  # Update then_block reference in case get_compiled created new blocks

        builder.position_at_start(else_block)
        if len(else_body_prop.compound_properties) == 0:
            raise CompileError('`else` block cannot be empty')
        for expr in else_body_prop.compound_properties:
            else_expr = expression_compile_all(expr, scope)
        else_val = get_compiled(else_expr, scope)
        builder.branch(merge_block) # go back to the main flow
        else_block = builder.block  # Update else_block reference in case get_compiled created new blocks

        # 3. Emit Merge Block and PHI
        builder.position_at_start(merge_block)
        phi = builder.phi(ir.IntType(64), 'iftmp')
        phi.add_incoming(then_val, then_block)  # If we came from then_block, result is the then_val
        phi.add_incoming(else_val, else_block)  # If we came from else_block, result is the body_val
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=phi)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompileDoDefinition(Definition):
    symbol = 'compile'
    property_names = ['do']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, body_prop = lhs.discard_properties_after('do')
        for expr in body_prop.compound_properties:
            expression_compile_all(expr, scope)
        res = get_compiled(lhs, scope)
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompileDefinition(Definition):
    symbol = 'compile_to'
    param_names = 'file_dest'
    @binary_apply
    def apply(self, lhs: Expression, file_dest: Expression, scope: Scope) -> Expression:
        if (path := file_dest.try_get_property('string')) is None:
            raise CompileError(f'compile destination must be a string, got {file_dest}')
        path_str = path.associated_value
        if not (path_str.endswith('.obj') or path_str.endswith('.out')):
            raise CompileError(f'compile destination must end with .obj or .out, got {file_dest}')

        module = ir.Module(path_str)
        target = llvm.Target.from_default_triple()
        target_machine = target.create_target_machine()
        module.triple = target_machine.triple
        module.data_layout = target_machine.target_data # type: ignore

        compile_scope = Scope(parent_scope=scope)
        func = ir.Function(module, ir.FunctionType(ir.IntType(64), []), name="main")
        builder = ir.IRBuilder(func.append_basic_block(name="entry"))
        _define_print_integer(module)
        _define_print_string(module)
        set_compile_construct(lhs.symbol, compile_scope, '__MODULE__', module)
        set_compile_construct(lhs.symbol, compile_scope, '__BUILDER__', builder)
        set_compile_construct(lhs.symbol, compile_scope, '__IMPORT_PATH__', path_str)

        from main import resolve_property_on
        compiled_expr = resolve_property_on(lhs, Property(lhs.symbol.create_renamed('compile')), compile_scope)
        compiled_val = get_compiled(compiled_expr, compile_scope)
        builder.ret(compiled_val)

        # Output compiled binary file
        llvm_ir = str(module)
        llvm_mod = llvm.parse_assembly(llvm_ir)
        llvm_mod.verify()

        obj_path_str = path_str.rsplit('.', 1)[0] + '.obj'
        with open(obj_path_str, 'wb') as f:
            f.write(target_machine.emit_object(llvm_mod))
        if path_str.endswith('.out'):
            import subprocess
            import os
            subprocess.run(['clang', obj_path_str, '-o', path_str])
            # clean up the object file
            os.remove(obj_path_str)

        return lhs