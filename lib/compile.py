from typing import Any, Callable, Collection
from typing_extensions import Literal

import llvmlite.ir as ir
import llvmlite.binding as llvm

from constants import Definition, Scope, PropertyContainerProtocol, PropertiesLookup, Expression, Property, Token
import constants
from definitions import register_definition, define_apply, get_context, update_context
from errors import perror, pwarning

llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

class CompileTypeProperties(PropertyContainerProtocol):
    def __init__(self, t: ir.Type, properties: list[Property]):
        self.properties = properties
        self.t = t

CompileConstruct = Literal['__MODULE__', '__IMPORT_PATH__', '__BUILDER__', '__TYPE_MAP__']
CompileConstructType = ir.Module | ir.IRBuilder | str | PropertiesLookup[CompileTypeProperties]

# compiled_result: generated values for compilation
# compile: property that triggers the compilation resolution over regular resolution

def get_compile_construct(scope: Scope, name: CompileConstruct) -> Any: # CompileConstructType
    module_expr = scope.force_var_lookup(name)
    module_compile_prop = module_expr.force_get_property('compiled_result')
    return module_compile_prop.associated_value

def set_compile_construct(anchor: Token, scope: Scope, name: CompileConstruct, value: CompileConstructType):
    scope.local_vars[name] = Expression(
        symbol=anchor.create_renamed(name),
        properties=[Property(anchor.create_renamed('compiled_result'), is_association=True, associated_value=value)]
    )

def _compile_last_property(expr: Expression, scope: Scope, additional_compound: list[Expression]) -> Expression:
    from main import resolve_last_property
    prop = expr.properties[-1]
    if prop.start_char != '{':
        prop.compound_properties = [expression_compile_all(local_expr, scope) for local_expr in prop.compound_properties]

    # There will be a 'compile' property inserted by expression_compile_all, so we resolve directly
    compiled_expr = resolve_last_property(expr, scope, additional_compound)
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
            expr_copy = _compile_last_property(expr_copy, scope, prop.compound_properties)
            # assert not any(p.property.s in constants.resolve for p in expr_copy.properties)
        else:
            expr_copy.properties.append(prop)
    return expr_copy


def get_compiled(expr: Expression, scope: Scope) -> ir.Value:
    compiled_prop = expr.try_get_property('compiled_result')
    if compiled_prop is None:
        # There are a few literal special cases that we want to compile without resolve
        # These are integers and strings
        if (int_prop := expr.try_get_property('integer')) is not None:
            return ir.Constant(ir.IntType(64), int_prop.associated_value or 0)
        elif (str_prop := expr.try_get_property('string')) is not None:
            return create_string(str_prop.associated_value, scope)
        perror(f"expression {expr} is not compiled", anchor=expr)
    return compiled_prop.associated_value

def _default_typemap(anchor: Token) -> PropertiesLookup[CompileTypeProperties]:
    return PropertiesLookup([
        CompileTypeProperties(ir.IntType(64), [Property(anchor.create_renamed('integer'))]),
        CompileTypeProperties(ir.PointerType(ir.IntType(8)), [Property(anchor.create_renamed('string'))]),
        CompileTypeProperties(ir.PointerType(ir.IntType(64)), [Property(anchor.create_renamed('pointer'))]), # TODO better type mapping for heterogenous pointers
        CompileTypeProperties(ir.PointerType(ir.IntType(8)), [Property(anchor.create_renamed('file'))]), # We will treat files as opaque pointers
        CompileTypeProperties(ir.PointerType(ir.IntType(8)), [Property(anchor.create_renamed('list'))]), # We will treat lists as opaque pointers
    ])

def get_type(expr: Expression, scope: Scope) -> ir.Type:
    type_map: PropertiesLookup[CompileTypeProperties] = get_compile_construct(scope, '__TYPE_MAP__')
    context = get_context(scope)
    score, match = type_map.lookup(expr.properties, context)
    if score < 0 or match is None:
        perror(f"Cannot determine type of expression '{expr}'", anchor=expr)
    return match.t

def size_of_type(type: ir.Type) -> int:
    # Returns the size of type in bytes
    if isinstance(type, ir.IntType):
        return max(1, (type.width + 7) // 8)
    if isinstance(type, ir.PointerType):
        # Default to a 64-bit pointer size when no target data is available.
        return 8
    if isinstance(type, ir.ArrayType):
        return type.count * size_of_type(type.element)
    if isinstance(type, ir.LiteralStructType):
        return sum(size_of_type(elem) for elem in type.elements)
    if hasattr(ir, 'IdentifiedStructType') and isinstance(type, ir.IdentifiedStructType):
        if getattr(type, 'is_opaque', False):
            perror(f"Cannot determine size of opaque struct type '{type}'")
        elements = getattr(type, 'elements', None)
        if elements is None:
            perror(f"Cannot determine size of struct type '{type}'")
        return sum(size_of_type(elem) for elem in elements)
    if isinstance(type, ir.FunctionType):
        perror(f"Cannot determine size of function type '{type}'")
    raise perror(f"Unsupported LLVM type for size calculation: '{type}'")

class CompiledUserDefinition(Definition):
    # To be stored as a "compile" definition on the func name
    @define_apply
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        args = [lhs] + args
        if len(args) < len(self.params):
            perror(f"not enough arguments provided to {self.prop_symb} (expected {self.params}, got {lhs}, {args})", anchor=lhs)
        args, var_args = args[:len(self.params)], args[len(self.params):]

        # make a call to the function
        builder = get_compile_construct(scope, '__BUILDER__')
        compiled_args = [get_compiled(expression_compile_all(arg, scope), scope) for arg in args]
        compiled_var_arg = get_compiled(compile_list(lhs, [expression_compile_all(arg, scope) for arg in var_args], scope), scope)
        arg_vals = compiled_args + [compiled_var_arg]

        module = get_compile_construct(scope, '__MODULE__')
        llvm_func = module.get_global(self.prop_symb)
        call_res = builder.call(llvm_func, arg_vals, self.prop_symb)
        compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=call_res)
        ret_prop = Property(lhs.symbol.create_renamed('integer'), is_association=True) # TODO better type handling
        return lhs.create_with_property(ret_prop).replace_property('compiled_result', compiled_prop)
    

# Builtin types

@register_definition('integer', ['compile'])
def compile_integer(lhs: Expression, prop: Property) -> Expression:
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True)
    compiled_prop.associated_value = ir.Constant(ir.IntType(64), prop.associated_value or 0)
    return lhs.create_with_property(prop).replace_property('compiled_result', compiled_prop)

compiled_string_cache: dict[tuple[str, str], ir.Value] = {}
def create_string(str_val: str, scope: Scope) -> ir.Value:
    builder: ir.IRBuilder = get_compile_construct(scope, '__BUILDER__')
    file_str = get_compile_construct(scope, '__IMPORT_PATH__')
    cache_key = (file_str, str_val)
    if cache_key in compiled_string_cache:
        return compiled_string_cache[cache_key]
    
    ty = ir.ArrayType(ir.IntType(8), len(str_val) + 1)
    shared_str = ir.GlobalVariable(
        get_compile_construct(scope, '__MODULE__'), 
        ty, name=f'str_{len(compiled_string_cache)}'
    )
    shared_str.linkage = 'internal'
    shared_str.global_constant = True
    shared_str.initializer = ir.Constant(ty, bytearray((str_val + '\0').encode("utf8"))) # type: ignore
    value: ir.Value = builder.bitcast(shared_str, ir.PointerType(ir.IntType(8))) # type: ignore
    compiled_string_cache[cache_key] = value
    return value

@register_definition('string', ['compile'])
def compile_string(lhs: Expression, scope: Scope, prop: Property) -> Expression:
    shared_str = create_string(prop.associated_value, scope)
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=shared_str)
    return lhs.create_with_property(prop).replace_property('compiled_result', compiled_prop)

# Operations on built-in types
def builtin_binary_op(op_symbol: str, op_name: str):
    def wrapper(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lhs_val = get_compiled(lhs, scope)
        rhs_val = get_compiled(rhs, scope)
        builder = get_compile_construct(scope, '__BUILDER__')
        res = getattr(builder, op_name)(lhs_val, rhs_val, f'{op_name}_tmp')
        compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
        return lhs.replace_property('compiled_result', compiled_prop)
    return register_definition(op_symbol, ['compile', 'integer'], ['operand'])(wrapper)

def builtin_compare_binary_op(cmp_type: str):
    def wrapper(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lhs_val = get_compiled(lhs, scope)
        rhs_val = get_compiled(rhs, scope)
        builder = get_compile_construct(scope, '__BUILDER__')
        cmp_res = builder.icmp_signed(cmp_type, lhs_val, rhs_val, f'{cmp_type}_tmp')
        ires = builder.zext(cmp_res, ir.IntType(64), f'{cmp_type}_bool_to_int_tmp')
        compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=ires)
        return lhs.replace_property('compiled_result', compiled_prop)
    return register_definition(cmp_type, ['compile', 'integer'], ['operand'])(wrapper)

builtin_binary_op('+', 'add')
builtin_binary_op('-', 'sub')
builtin_binary_op('*', 'mul')
builtin_binary_op('/', 'sdiv')
builtin_compare_binary_op('==')
builtin_compare_binary_op('!=')
builtin_compare_binary_op('<')
builtin_compare_binary_op('>')
builtin_compare_binary_op('<=')
builtin_compare_binary_op('>=')

@register_definition('logical_not', ['compile', 'integer'])
def compile_logical_not(lhs: Expression, scope: Scope) -> Expression:
    lhs, _ = lhs.discard_properties_after('logical_not')
    builder = get_compile_construct(scope, '__BUILDER__')
    lhs_val = get_compiled(lhs, scope)
    zero = ir.Constant(ir.IntType(64), 0)
    cmp_res = builder.icmp_signed('!=', lhs_val, zero, 'logical_not_tmp')
    ires = builder.zext(cmp_res, ir.IntType(64), 'bool_to_int_tmp')
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=ires)
    return lhs.replace_property('compiled_result', compiled_prop)

# Variables

def create_variable(name: str, scope: Scope, base_properties: Expression) -> Expression:
    # Determine the "type" of the variable from base_properties
    var_type = get_type(base_properties, scope)
    if scope.is_global:
        var = ir.GlobalVariable(get_compile_construct(scope, '__MODULE__'), var_type, name=name)
        var.linkage = 'internal'
    else:
        builder = get_compile_construct(scope, '__BUILDER__')
        var = builder.alloca(var_type, name=name)
    anchor = base_properties.symbol
    compiled_prop = Property(anchor.create_renamed('compiled_result'), is_association=True, associated_value=var)
    res = scope.local_vars[name] = base_properties.replace_property('compiled_result', compiled_prop)
    return res

@register_definition('identifier', ['compile'])
def compile_identifier(lhs: Expression, scope: Scope) -> Expression:
    var_expr = scope.var_lookup(lhs.symbol.s)
    if var_expr is None:
        return pwarning(f"Undefined variable '{lhs.symbol.s}'", anchor=lhs)
    builder = get_compile_construct(scope, '__BUILDER__')
    if var_expr.try_get_property('argument') is None:
        var_ptr = get_compiled(var_expr, scope)
        var_val = builder.load(var_ptr, f'{lhs.symbol.s}_val')
    else:
        var_val = get_compiled(var_expr, scope)
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=var_val)
    # We want to put the identifier properties before all the var_expr properties
    res = Expression(lhs.symbol, lhs.properties + var_expr.properties)
    return res.replace_property('compiled_result', compiled_prop)

@register_definition('declare', ['compile'])
def compile_declare(lhs: Expression, scope: Scope) -> Expression:
    return create_variable(lhs.symbol.s, scope, lhs)

    
@register_definition('assign', ['compile', 'identifier'])
def compile_assign(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    val_expr = expression_compile_all(rhs, scope)  # compile the rhs
    var_expr = scope.var_lookup(lhs.symbol.s)
    if var_expr is None:
        var_expr = create_variable(lhs.symbol.s, scope, val_expr)
    # TODO move properties of val_expr to var_expr
    var = get_compiled(var_expr, scope)
    val = get_compiled(val_expr, scope)
    if not all(val_expr.try_get_property(p.property.s) for p in var_expr.properties):
        return pwarning(f"Type mismatch in assignment to variable '{lhs.symbol.s}'", anchor=lhs)
    builder = get_compile_construct(scope, '__BUILDER__')
    compile_res = builder.store(val, var)
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=compile_res)
    return lhs.replace_property('compiled_result', compiled_prop)

# Conditionals

@register_definition('then', ['compile', 'integer'])
def compile_then(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    cond_val = get_compiled(lhs, scope)
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
    if len(body) == 0:
        return pwarning('`then` block cannot be empty', anchor=lhs)
    for expr in body:
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
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=phi)
    return lhs.replace_property('compiled_result', compiled_prop)

@register_definition('else', ['compile', 'integer'])
def compile_else(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    cond_val = get_compiled(lhs, scope)
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
    if len(body) == 0:
        return pwarning('`else` block cannot be empty', anchor=lhs)
    for expr in body:
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
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=phi)
    return lhs.replace_property('compiled_result', compiled_prop)

@register_definition('else', ['compile', 'integer', 'then'])
def compile_then_else(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    cond_expr, then_body_prop = lhs.discard_properties_after('then')
    then_body = then_body_prop.compound_properties
    else_body = body

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
    if len(then_body) == 0:
        return pwarning('`then` block cannot be empty', anchor=lhs)
    for expr in then_body:
        then_expr = expression_compile_all(expr, scope)
    then_val = get_compiled(then_expr, scope)
    builder.branch(merge_block) # go back to the main flow
    then_block = builder.block  # Update then_block reference in case get_compiled created new blocks

    builder.position_at_start(else_block)
    if len(else_body) == 0:
        return pwarning('`else` block cannot be empty', anchor=lhs)
    for expr in else_body:
        else_expr = expression_compile_all(expr, scope)
    else_val = get_compiled(else_expr, scope)
    builder.branch(merge_block) # go back to the main flow
    else_block = builder.block  # Update else_block reference in case get_compiled created new blocks

    # 3. Emit Merge Block and PHI
    builder.position_at_start(merge_block)
    phi = builder.phi(ir.IntType(64), 'iftmp')
    phi.add_incoming(then_val, then_block)  # If we came from then_block, result is the then_val
    phi.add_incoming(else_val, else_block)  # If we came from else_block, result is the body_val
    compiled_prop = Property(cond_expr.symbol.create_renamed('compiled_result'), is_association=True, associated_value=phi)
    return cond_expr.replace_property('compiled_result', compiled_prop)

@register_definition('do', ['compile'])
def compile_do(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    for expr in body:
        expression_compile_all(expr, scope)
    ret_val = get_compiled(lhs, scope)
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=ret_val)
    return lhs.replace_property('compiled_result', compiled_prop)

@register_definition('definition', ['compile'], ['body...'])
def compile_definition(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    # The function property is the last property in lhs
    # TODO name mangling to allow multiple functions with the same name but different signatures
    # The parameters are the lhs symbol and the symbols in the compound properties of the last property in the lhs
    lhs = lhs.discard_property('identifier')
    *lhs.properties, func_prop = lhs.properties
    func_name = func_prop.property.s
    # TODO types for parameters and return value
    params = [lhs] + func_prop.compound_properties
    params = [param.discard_property('identifier') for param in params]
    vararg = Expression(symbol=lhs.symbol.create_renamed('arguments'), properties=[Property(lhs.symbol.create_renamed('list'))])
    arg_types = [get_type(param, scope) for param in params] + [get_type(vararg, scope)]

    # TODO return a non-integer type
    compile_prop = Property(lhs.symbol.create_renamed('compile'))
    func = ir.Function(get_compile_construct(scope, '__MODULE__'), ir.FunctionType(ir.IntType(64), arg_types), name=func_name)
    defn = CompiledUserDefinition(func_name, [compile_prop] + lhs.properties, is_compound=True, params=params, body=[], scope=scope)
    block = func.append_basic_block(name=func_name)
    scope.local_defns.setdefault(func_name, []).append(defn)

    compile_scope = Scope(parent_scope=scope)
    builder = ir.IRBuilder(block)
    set_compile_construct(lhs.symbol, compile_scope, '__BUILDER__', builder)
    # Populate parameters
    compiled_token = lhs.symbol.create_renamed('compiled_result')
    arg_prop = Property(lhs.symbol.create_renamed('argument'))
    for param, arg in zip(params, func.args):
        compiled_prop = Property(compiled_token, is_association=True, associated_value=arg)
        compile_scope.local_vars[param.symbol.s] = Expression(
            symbol=param.symbol,
            properties=[compiled_prop, arg_prop] + param.properties
        )
    vararg_compiled_prop = Property(compiled_token, is_association=True, associated_value=func.args[len(params)])
    compile_scope.local_vars[vararg.symbol.s] = Expression(
        symbol=vararg.symbol,
        properties=[vararg_compiled_prop, arg_prop] + vararg.properties
    )

    for expr in body:
        res_expr = expression_compile_all(expr, compile_scope)
    res = get_compiled(res_expr, compile_scope)
    builder.ret(res)

    property_prop = Property(func_prop.property.create_renamed('property'))
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=func)
    return Expression(func_prop.property, [compiled_prop, compiled_prop, property_prop])

# Lists (we need this for variadic args)

# This file only implements `compile list(...)`, the rest are implemented in `list.lang`
# A list is implemented as a contiguous memory with a size header for each item
# followed by the item data. After the last item is a terminating 64-bit size = 0
# <64-bit size> <item of size> <64-bit size> <item of size> ... <64-bit size = 0>
@register_definition('list', ['compile'], ['items...'])
def compile_list(lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
    '''lhs is an anchor; none of its properties are relevant'''
    builder: ir.IRBuilder = get_compile_construct(scope, '__BUILDER__')
    module: ir.Module = get_compile_construct(scope, '__MODULE__')

    item_sizes = []
    int_size = size_of_type(ir.IntType(64))
    total_size = int_size * (len(args) + 1) # +1 for the terminating 0 size
    for arg in args:
        arg_type: ir.Type = get_type(arg, scope)
        arg_size = size_of_type(arg_type) # TODO make sure that this works with alignment
        total_size += arg_size
        item_sizes.append((arg_type, arg_size))
    
    output_ptr = builder.call(module.get_global('malloc'), [ir.Constant(ir.IntType(64), total_size)], 'malloc_tmp')
    current_ptr = output_ptr
    for arg, (arg_type, arg_size) in zip(args, item_sizes):
        builder.store(ir.Constant(ir.IntType(64), arg_size), builder.bitcast(current_ptr, ir.PointerType(ir.IntType(64))))
        current_ptr = builder.gep(current_ptr, [ir.Constant(ir.IntType(64), int_size)])
        arg_val = get_compiled(arg, scope)
        builder.store(arg_val, builder.bitcast(current_ptr, ir.PointerType(arg_type)))
        current_ptr = builder.gep(current_ptr, [ir.Constant(ir.IntType(64), arg_size)])
    builder.store(ir.Constant(ir.IntType(64), 0), builder.bitcast(current_ptr, ir.PointerType(ir.IntType(64))))
    
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=output_ptr)
    list_prop = Property(lhs.symbol.create_renamed('list'))
    return lhs.create_with_property(list_prop).replace_property('compiled_result', compiled_prop)

@register_definition('list', ['compile', 'pointer'])
def compile_list_from_pointer(lhs: Expression, scope: Scope, prop: Property) -> Expression:
    builder: ir.IRBuilder = get_compile_construct(scope, '__BUILDER__')
    ptr_value = get_compiled(lhs, scope)
    # Cast to pointer to int8
    ptr_value = builder.bitcast(ptr_value, ir.PointerType(ir.IntType(8)))
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=ptr_value)
    return lhs.replace_property('pointer', prop).replace_property('compiled_result', compiled_prop)

# TODO make the compilation imports/linking more explicit
imported_modules: dict[str, tuple[ir.Module, Collection[ir.Function]]] = {}

# Create all cstdlib function declarations
def _cstdlib_module():
    module = ir.Module(name="stdlib")
    module.triple = llvm.Target.from_default_triple().triple
    module.data_layout = llvm.Target.from_default_triple().create_target_machine().target_data # type: ignore

    # stdlib
    ir.Function(module, ir.FunctionType(ir.PointerType(ir.IntType(8)), [ir.IntType(64)]), name="malloc")
    ir.Function(module, ir.FunctionType(ir.PointerType(ir.IntType(8)), [ir.PointerType(ir.IntType(8)), ir.IntType(64)]), name="realloc")
    ir.Function(module, ir.FunctionType(ir.VoidType(), [ir.PointerType(ir.IntType(8))]), name="free")
    # stdio
    ir.Function(module, ir.FunctionType(ir.PointerType(ir.IntType(8)), [ir.PointerType(ir.IntType(8)), ir.PointerType(ir.IntType(8))]), name="fopen")
    ir.Function(module, ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))]), name="fclose")
    ir.Function(module, ir.FunctionType(ir.IntType(64), [ir.PointerType(ir.IntType(8)), ir.IntType(64), ir.IntType(64), ir.PointerType(ir.IntType(8))]), name="fread")
    ir.Function(module, ir.FunctionType(ir.IntType(64), [ir.PointerType(ir.IntType(8)), ir.IntType(64), ir.IntType(64), ir.PointerType(ir.IntType(8))]), name="fwrite")
    ir.Function(module, ir.FunctionType(ir.IntType(64), [ir.PointerType(ir.IntType(8))]), name="ftell")
    ir.Function(module, ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8)), ir.IntType(64), ir.IntType(32)]), name="fseek")
    ir.Function(module, ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))], var_arg=True), name="printf")
    ir.Function(module, ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))]), name="puts")
    ir.Function(module, ir.FunctionType(ir.VoidType(), [ir.PointerType(ir.IntType(8))]), name="fflush")
    # string
    ir.Function(module, ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8)), ir.PointerType(ir.IntType(8))]), name='strcmp')
    ir.Function(module, ir.FunctionType(ir.PointerType(ir.IntType(8)), [ir.PointerType(ir.IntType(8)), ir.PointerType(ir.IntType(8))]), name='strcpy')
    ir.Function(module, ir.FunctionType(ir.PointerType(ir.IntType(8)), [ir.PointerType(ir.IntType(8)), ir.PointerType(ir.IntType(8))]), name='strcat')
    ir.Function(module, ir.FunctionType(ir.IntType(64), [ir.PointerType(ir.IntType(8))]), name='strlen')
    ir.Function(module, ir.FunctionType(ir.PointerType(ir.IntType(8)), [ir.PointerType(ir.IntType(8)), ir.PointerType(ir.IntType(8))]), name='strtok')
    return module

def _imported_signature(src:ir.Module, exclude: Collection[ir.Function] = []) -> tuple[ir.Module, Collection[ir.Function]]:
    return src, [func for func in src.functions if func not in exclude]

# Module for our own stdlib functions
imported_modules['stdlib'] = _imported_signature(_cstdlib_module())

def add_stdlib_definition(callback: Callable[[ir.Module], None]):
    module, old = imported_modules['stdlib']
    callback(module)
    imported_modules['stdlib'] = _imported_signature(module)

def inherit_declarations(dst:ir.Module):
    inherited = set()
    for module, functions in imported_modules.values():
        for func in functions:
            added = ir.Function(dst, func.function_type, name=func.name)
            inherited.add(added)
        # TODO Also add declarations for when we later want to link global variables
    return inherited
    
# TODO this is unused
def register_constructor(module: ir.Module, func: ir.Function):
    ctor_struct_ty = ir.LiteralStructType([ir.IntType(32), func.type, ir.IntType(8).as_pointer()])
    ctors_array_ty = ir.ArrayType(ctor_struct_ty, 1)
    ctor_struct = ir.Constant.literal_struct([ir.Constant(ir.IntType(32), 65535), func, ir.Constant(ir.IntType(8).as_pointer(), None)])
    ctors_init = ir.Constant(ctors_array_ty, [ctor_struct])
    global_ctors = ir.GlobalVariable(module, ctors_array_ty, name="llvm.global_ctors")
    global_ctors.linkage = "appending"
    global_ctors.initializer = ctors_init # type: ignore

anonymous_module_num = 0
@register_definition('import', ['compile'], ['signatures...'])
def compile_import(lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
    lhs = lhs.discard_property('compile')   # We treat `compile import` as one op

    global anonymous_module_num
    name = f'anonymous_module_{anonymous_module_num}'
    anonymous_module_num += 1

    module = ir.Module(name)
    target = llvm.Target.from_default_triple()
    target_machine = target.create_target_machine()
    module.triple = target_machine.triple
    module.data_layout = target_machine.target_data # type: ignore

    # TODO cache the compiled results
    compile_scope = Scope(parent_scope=scope)
    update_context(Expression(lhs.symbol.create_renamed('__CONTEXT__'), [Property(lhs.symbol.create_renamed('compile'))]), compile_scope)

    func_ty = ir.FunctionType(ir.IntType(64), [])
    func = ir.Function(module, func_ty, name=name)
    builder = ir.IRBuilder(func.append_basic_block(name="entry"))
    set_compile_construct(lhs.symbol, compile_scope, '__MODULE__', module)
    set_compile_construct(lhs.symbol, compile_scope, '__BUILDER__', builder)
    set_compile_construct(lhs.symbol, compile_scope, '__IMPORT_PATH__', name)
    set_compile_construct(lhs.symbol, compile_scope, '__TYPE_MAP__', _default_typemap(lhs.symbol))

    inherited = inherit_declarations(module)
    resolution_property = Property(lhs.symbol.create_renamed('.'))
    compiled_expr = expression_compile_all(lhs.create_with_property(resolution_property), compile_scope)
    compiled_val = get_compiled(compiled_expr, compile_scope)
    builder.ret(compiled_val)

    # Output module 
    imported_modules[name] = _imported_signature(module, inherited)
    
    # Export global definitions as well
    for arg in args:
        found_all = compile_scope.defn_lookup_recursive(arg.symbol.s)
        found = found_all.list_all()
        if len(found) == 0:
            return pwarning(f"Cannot find definition for '{arg.symbol.s}' to import", anchor=arg)
        for defn in found:
            scope.local_defns.setdefault(defn.prop_symb, []).append(defn)
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=module)
    return Expression(lhs.symbol.create_renamed(name), lhs.properties).replace_property('compiled_result', compiled_prop)

@register_definition('compile_to', [], ['file_dest'])
def compile_to(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    if (path := rhs.try_get_property('string')) is None:
        return pwarning(f'compile destination must be a string, got {rhs}', anchor=rhs)
    path_str = path.associated_value
    if not (path_str.endswith('.obj') or path_str.endswith('.out')):
        return pwarning(f'compile destination must end with .obj or .out, got {rhs}', anchor=rhs)

    module = ir.Module(path_str)
    target = llvm.Target.from_default_triple()
    target_machine = target.create_target_machine()
    module.triple = target_machine.triple
    module.data_layout = target_machine.target_data # type: ignore

    compile_scope = Scope(parent_scope=scope)
    update_context(Expression(lhs.symbol.create_renamed('__CONTEXT__'), [Property(lhs.symbol.create_renamed('compile'))]), compile_scope)

    func = ir.Function(module, ir.FunctionType(ir.IntType(64), []), name="main")
    builder = ir.IRBuilder(func.append_basic_block(name="entry"))
    set_compile_construct(lhs.symbol, compile_scope, '__MODULE__', module)
    set_compile_construct(lhs.symbol, compile_scope, '__BUILDER__', builder)
    set_compile_construct(lhs.symbol, compile_scope, '__IMPORT_PATH__', path_str)
    set_compile_construct(lhs.symbol, compile_scope, '__TYPE_MAP__', _default_typemap(lhs.symbol))

    inherited = inherit_declarations(module) # Add type definitions to module
    resolution_property = Property(lhs.symbol.create_renamed('.'))
    compiled_expr = expression_compile_all(lhs.create_with_property(resolution_property), compile_scope)
    compiled_val = get_compiled(compiled_expr, compile_scope)
    builder.ret(compiled_val)

    # Output compiled binary file
    llvm_ir = str(module)
    # print(llvm_ir)
    llvm_mod = llvm.parse_assembly(llvm_ir)
    for module, functions in imported_modules.values():
        module_ir = str(module)
        imported_mod = llvm.parse_assembly(module_ir)
        imported_mod.verify()
        llvm_mod.link_in(imported_mod)
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
    
@register_definition('machine_name', ['compile'])
def compile_machine_name(lhs: Expression) -> Expression:
     target = llvm.Target.from_default_triple()
     machine_name = target.name
     string_prop = Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=machine_name)
     return Expression(lhs.symbol, properties=[string_prop])