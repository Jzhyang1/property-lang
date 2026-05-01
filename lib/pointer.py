if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, binary_apply, idempotent_apply, pwarning, CompileError

# We extend compilation
import llvmlite.ir as ir
if 'definitions' in globals():
    compile = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'compile.py')
else:
    raise ImportError("definitions module not found, cannot import compile module")

@builtin_definition
class PointerDefinition(Definition):
    symbol = 'pointer'
    @idempotent_apply
    def apply(self): pass
    
@builtin_definition
class DereferenceDefinition(Definition):
    symbol = 'dereference'
    property_names = ['pointer']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        ptr_prop = lhs.force_get_property('pointer')
        # The associated value is simply the Expression to return
        # every variable has a fixed expression that will not be reassigned
        return ptr_prop.associated_value
    
@builtin_definition
class ReferenceDefinition(Definition):
    symbol = 'reference'
    property_names = ['identifier']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        name = lhs.symbol.s
        associated_expr = scope.var_lookup(name)
        if associated_expr is None:
            raise CompileError(f"Undefined variable '{name}'")
        ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=associated_expr)
        return lhs.create_with_property(ptr_prop)
    

# Compilation

@builtin_definition
class CompilePointerDefinition(Definition):
    symbol = 'compile'
    property_names = ['pointer']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        raw_value = compile.get_compiled(lhs, scope)
        # llvm ir wants pointer type, so we cast the raw value to a pointer type
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        res = builder.bitcast(raw_value, ir.PointerType(ir.IntType(64)))
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompileDereferenceDefinition(Definition):
    symbol = 'compile'
    property_names = ['dereference']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        ptr_value = compile.get_compiled(lhs, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        ptr_value_ptr = builder.inttoptr(ptr_value, ir.PointerType(ir.IntType(64)))
        res = builder.load(ptr_value_ptr)
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompileReferenceDefinition(Definition):
    symbol = 'compile'
    property_names = ['reference']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        # We need to get the address of the variable being referenced
        name = lhs.symbol.s
        var = scope.var_lookup(name)
        if var is None:
            raise CompileError(f"Undefined variable '{name}'")
        var_ptr = compile.get_compiled(var, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        var_ptr_int = builder.ptrtoint(var_ptr, ir.IntType(64))
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=var_ptr_int)
        int_property = Property(lhs.symbol.create_renamed('integer'))
        return lhs.create_with_property(int_property).replace_property('compile', compile_prop)
