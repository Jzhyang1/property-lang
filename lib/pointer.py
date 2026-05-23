from constants import Definition, Scope, Expression, Property, Token
from definitions import register_definition, CompileError
import definitions

# We extend compilation
import llvmlite.ir as ir
compile = definitions.import_module(__file__, 'compile.py')

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
    
@register_definition('pointer')
def pointer(lhs: Expression, prop: Property) -> Expression:
    return lhs.create_with_property(prop)

@register_definition('dereference', ['pointer'])
def dereference(lhs: Expression) -> Expression:
    ptr_prop = lhs.force_get_property('pointer')
    # The associated value is simply the Expression to return
    # every variable has a fixed expression that will not be reassigned
    return ptr_prop.associated_value.get()

@register_definition('assign', ['pointer', 'dereference'])
def dereference_assign(lhs: Expression, rhs: Expression) -> Expression:
    ptr_prop = lhs.force_get_property('pointer')
    ptr_prop.associated_value.set(rhs)
    return rhs

@register_definition('reference', ['identifier'])
def reference(lhs: Expression, scope: Scope) -> Expression:
    name = lhs.symbol.s
    associated_expr = scope.var_lookup(name)
    if associated_expr is None:
        raise CompileError(f"Undefined variable '{name}'")
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=PointedTo([associated_expr]))
    return lhs.create_with_property(ptr_prop)

@register_definition('allocate', [], ['count'])
def allocate(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    count = rhs.force_get_property('integer').associated_value
    if count < 0:
        raise CompileError(f"Cannot allocate negative count {count}", anchor=rhs.symbol)
    allocated = [lhs.copy() for _ in range(count)]
    # Create an Expression that is not associated with any variable
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=PointedTo(allocated))
    return lhs.create_with_property(ptr_prop)

@register_definition('reallocate', ['pointer'], ['new_count'])
def reallocate(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    new_count = rhs.force_get_property('integer').associated_value
    if new_count < 0:
        raise CompileError(f"Cannot reallocate to negative count {new_count}", anchor=rhs.symbol)
    ptr_prop = lhs.force_get_property('pointer')
    old_pointed_to = ptr_prop.associated_value
    old_items = old_pointed_to.items
    new_items = old_items[:new_count] + [lhs.copy() for _ in range(max(0, new_count - len(old_items)))]
    new_pointed_to = PointedTo(new_items)
    new_ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=new_pointed_to)
    return lhs.create_with_property(new_ptr_prop)

@register_definition('+', ['pointer'], ['offset'])
def pointer_advance(lhs: Expression, rhs: Expression) -> Expression:
    offset = rhs.force_get_property('integer').associated_value
    ptr_prop = lhs.force_get_property('pointer')
    new_ptr = ptr_prop.associated_value.advance(offset)
    new_ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=new_ptr)
    return lhs.create_with_property(new_ptr_prop)

@register_definition('-', ['pointer'], ['offset'])
def pointer_retreat(lhs: Expression, rhs: Expression) -> Expression:
    offset = rhs.force_get_property('integer').associated_value
    ptr_prop = lhs.force_get_property('pointer')
    new_ptr = ptr_prop.associated_value.advance(-offset)
    new_ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=new_ptr)
    return lhs.create_with_property(new_ptr_prop)

# Compilation

@register_definition('pointer', ['compile'])
def compile_pointer(lhs: Expression, scope: Scope) -> Expression:
    raw_value = compile.get_compiled(lhs, scope)
    # llvm ir wants pointer type, so we cast the raw value to a pointer type
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    res = builder.inttoptr(raw_value, ir.PointerType(ir.IntType(64)))
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
    return lhs.replace_property('compiled_result', compile_prop)

@register_definition('dereference', ['compile', 'pointer'])
def compile_dereference(lhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    res = builder.load(ptr_value)
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
    return lhs.replace_property('pointer', Property(lhs.symbol.create_renamed('integer'))).replace_property('compiled_result', compile_prop)

@register_definition('assign', ['compile', 'pointer', 'dereference'])
def compile_dereference_assign(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    rhs_value = compile.get_compiled(rhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    builder.store(rhs_value, ptr_value)
    return rhs

@register_definition('reference', ['compile', 'identifier'])
def compile_reference(lhs: Expression, scope: Scope) -> Expression:
    # We need to get the address of the variable being referenced
    name = lhs.symbol.s
    var = scope.var_lookup(name)
    if var is None:
        raise CompileError(f"Undefined variable '{name}'")
    var_ptr = compile.get_compiled(var, scope)
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=var_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compile_prop)

@register_definition('allocate', ['compile'], ['count'])
def compile_allocate(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    count_value = compile.get_compiled(rhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')
    allocated_ptr = builder.call(module.get_global('malloc'), [count_value])
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=allocated_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compile_prop)

@register_definition('deallocate', ['compile', 'pointer'])
def compile_deallocate(lhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')
    builder.call(module.get_global('free'), [ptr_value])
    return lhs

@register_definition('reallocate', ['compile', 'pointer'], ['new_count'])
def compile_reallocate(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    new_count_value = compile.get_compiled(rhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')
    res_ptr = builder.call(module.get_global('realloc'), [ptr_value, new_count_value])
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compile_prop)

@register_definition('+', ['compile', 'pointer'], ['offset'])
def compile_pointer_advance(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    offset_value = compile.get_compiled(rhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    res_ptr = builder.gep(ptr_value, [offset_value])
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compile_prop)

@register_definition('-', ['compile', 'pointer'], ['offset'])
def compile_pointer_retreat(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    offset_value = compile.get_compiled(rhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    res_ptr = builder.gep(ptr_value, [builder.neg(offset_value)])
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compile_prop)