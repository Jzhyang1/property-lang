if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, binary_apply, idempotent_apply, pwarning, CompileError

# We extend compilation
import llvmlite.ir as ir
if 'definitions' in globals():
    compile = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'compile.py')
else:
    raise ImportError("definitions module not found, cannot import compile module")

class PointedTo:
    def __init__(self, items: list[Expression], index: int = 0):
        self.items = items
        self.index = index
    def get(self):
        return self.items[self.index]
    def set(self, value: Expression):
        self.items[self.index] = value
    def advance(self, value):
        return PointedTo(self.items, self.index + value)

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
        return ptr_prop.associated_value.get()
    
@builtin_definition
class DereferenceAssignDefinition(Definition):
    symbol = 'assign'
    property_names = ['pointer', 'dereference']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        ptr_prop = lhs.force_get_property('pointer')
        ptr_prop.associated_value.set(rhs)
        return rhs
    
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
        ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=PointedTo([associated_expr]))
        return lhs.create_with_property(ptr_prop)
    
@builtin_definition
class AllocateDefinition(Definition):
    # Allocates a binary block of the given size in bytes and returns a pointer to it
    symbol = 'allocate'
    # property_names = <any property that is a type> # TODO enforce
    param_names = ['count']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        size = rhs.force_get_property('integer').associated_value
        if size < 0:
            raise CompileError(f"Cannot allocate negative size {size}", anchor=rhs.symbol)
        allocated = [lhs.copy() for _ in range(size)]
        # Create an Expression that is not associated with any variable
        ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=PointedTo(allocated))
        return lhs.create_with_property(ptr_prop)
    
@builtin_definition
class ReallocateDefinition(Definition):
    symbol = 'reallocate'
    property_names = ['pointer', 'reallocate']
    param_names = ['new_size']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        new_size = rhs.force_get_property('integer').associated_value
        if new_size < 0:
            raise CompileError(f"Cannot reallocate to negative size {new_size}", anchor=rhs.symbol)
        ptr_prop = lhs.force_get_property('pointer')
        old_pointed_to = ptr_prop.associated_value
        old_items = old_pointed_to.items
        new_items = old_items[:new_size] + [lhs.copy() for _ in range(max(0, new_size - len(old_items)))]
        new_pointed_to = PointedTo(new_items)
        new_ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=new_pointed_to)
        return lhs.create_with_property(new_ptr_prop)

@builtin_definition
class PointerAddDefinition(Definition):
    symbol = '+'
    property_names = ['pointer']
    param_names = ['offset']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        offset = rhs.force_get_property('integer').associated_value
        ptr_prop = lhs.force_get_property('pointer')
        new_ptr = ptr_prop.associated_value.advance(offset)
        new_ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=new_ptr)
        return lhs.create_with_property(new_ptr_prop)
    
@builtin_definition
class PointerSubtractDefinition(Definition):
    symbol = '-'
    property_names = ['pointer']
    param_names = ['offset']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        offset = rhs.force_get_property('integer').associated_value
        ptr_prop = lhs.force_get_property('pointer')
        new_ptr = ptr_prop.associated_value.advance(-offset)
        new_ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=new_ptr)
        return lhs.create_with_property(new_ptr_prop)

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
class CompileDereferenceAssignDefinition(Definition):
    symbol = 'compile'
    property_names = ['pointer', 'dereference', 'assign']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, assign_prop = lhs.discard_properties_after('assign')
        if len(assign_prop.compound_properties) != 1:
            raise CompileError("expected exactly one property after 'assign' for pointer assignment", anchor=assign_prop.property)
        rhs_expr = assign_prop.compound_properties[0]
        ptr_value = compile.get_compiled(lhs, scope) # Should be of type ir.PointerType
        rhs_value = compile.get_compiled(rhs_expr, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        builder.store(rhs_value, ptr_value)
        return lhs

@builtin_definition
class CompileReferenceDefinition(Definition):
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
    
@builtin_definition
class CompilePointerAddDefinition(Definition):
    symbol = 'compile'
    property_names = ['pointer']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, offset_prop = lhs.discard_properties_after('+')
        if len(offset_prop.compound_properties) != 1:
            raise CompileError("expected exactly one property after '+' for pointer addition", anchor=offset_prop.property)
        offset_expr = offset_prop.compound_properties[0]
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        ptr_value = compile.get_compiled(lhs, scope)
        offset_value = compile.get_compiled(offset_expr, scope)
        res_ptr = builder.gep(ptr_value, [offset_value])
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res_ptr)
        ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
        return lhs.create_with_property(ptr_prop).replace_property('compile', compile_prop)
    
@builtin_definition
class CompilePointerSubtractDefinition(Definition):
    symbol = 'compile'
    property_names = ['pointer']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, offset_prop = lhs.discard_properties_after('-')
        if len(offset_prop.compound_properties) != 1:
            raise CompileError("expected exactly one property after '-' for pointer subtraction", anchor=offset_prop.property)
        offset_expr = offset_prop.compound_properties[0]
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        ptr_value = compile.get_compiled(lhs, scope)
        offset_value = compile.get_compiled(offset_expr, scope)
        res_ptr = builder.gep(ptr_value, [builder.neg(offset_value)])
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res_ptr)
        ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
        return lhs.create_with_property(ptr_prop).replace_property('compile', compile_prop)