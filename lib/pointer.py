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
    
@builtin_definition
class AllocateDefinition(Definition):
    # Allocates a binary block of the given size in bytes and returns a pointer to it
    symbol = 'allocate'
    param_names = ['value'] # TODO given the form: _ type allocate(count), allocate count of type
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        size = lhs.force_get_property('integer').associated_value
        if size < 0:
            raise CompileError(f"Cannot allocate negative size {size}", anchor=lhs.symbol)
        # Create an Expression that is not associated with any variable
        allocated = Expression(lhs.symbol.create_renamed('allocated'), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=0)
        ])
        ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=allocated)
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
        res = builder.inttoptr(raw_value, ir.PointerType(ir.IntType(64)))
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompileDereferenceDefinition(Definition):
    symbol = 'compile'
    property_names = ['pointer', 'dereference']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        ptr_value = compile.get_compiled(lhs, scope) # Should be of type ir.PointerType
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        res = builder.load(ptr_value)
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompileReferenceDefinition(Definition):
    # TODO we can use pointers now (instead of casting everything to int)
    symbol = 'compile'
    property_names = ['identifier', 'reference']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        # We need to get the address of the variable being referenced
        name = lhs.symbol.s
        var = scope.var_lookup(name)
        if var is None:
            raise CompileError(f"Undefined variable '{name}'")
        var_ptr = compile.get_compiled(var, scope)
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=var_ptr)
        ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
        return lhs.create_with_property(ptr_prop).replace_property('compile', compile_prop)

@builtin_definition
class CompileAllocateDefinition(Definition):
    symbol = 'compile'
    property_names = ['allocate']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        size_value = compile.get_compiled(lhs, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        # We must call malloc because size_value is not a constant
        allocated_ptr = builder.call(builder.get_global('malloc'), [size_value])
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=allocated_ptr)
        ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
        return lhs.create_with_property(ptr_prop).replace_property('compile', compile_prop)
    
@builtin_definition
class CompileDeallocateDefinition(Definition):
    symbol = 'compile'
    property_names = ['pointer', 'deallocate']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        ptr_value = compile.get_compiled(lhs, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        builder.call(builder.get_global('free'), [ptr_value])
        return lhs
    
@builtin_definition
class CompileReallocateDefinition(Definition):
    symbol = 'compile'
    property_names = ['pointer', 'reallocate']
    param_names = ['new_size']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, rprop = lhs.discard_properties_after('reallocate')
        if len(rprop.compound_properties) != 1:
            raise CompileError("expected exactly one property after 'reallocate' for pointer reallocation", anchor=rprop.property)
        new_size_expr = rprop.compound_properties[0]
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        module = compile.get_compile_construct(scope, '__MODULE__')

        ptr_value = compile.get_compiled(lhs, scope)
        new_size_value = compile.get_compiled(new_size_expr, scope)
        res_ptr = builder.call(module.get_global('realloc'), [ptr_value, new_size_value])
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res_ptr)
        ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
        return lhs.create_with_property(ptr_prop).replace_property('compile', compile_prop)