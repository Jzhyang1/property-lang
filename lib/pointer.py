from constants import Definition, Provenance, Scope, Expression, Property, Token
from errors import perror, pwarning
from definitions import register_definition
import imports

# We extend compilation
import llvmlite.ir as ir
compile = imports.import_module(Provenance.here(), 'compile.py')

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
        return pwarning(f"Undefined variable '{name}'", anchor=lhs)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=PointedTo([associated_expr]))
    return lhs.create_with_property(ptr_prop)

@register_definition('allocate', [], [('count', ['integer'])])
def allocate(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    count = rhs.force_get_property('integer').associated_value
    if count < 0:
        return pwarning(f"Cannot allocate negative count {count}", anchor=rhs)
    allocated = [lhs.copy() for _ in range(count)]
    # Create an Expression that is not associated with any variable
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'), is_association=True, associated_value=PointedTo(allocated))
    return lhs.create_with_property(ptr_prop)

@register_definition('reallocate', ['pointer'], [('new_count', ['integer'])])
def reallocate(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    new_count = rhs.force_get_property('integer').associated_value
    if new_count < 0:
        return pwarning(f"Cannot reallocate to negative count {new_count}", anchor=rhs)
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

@register_definition('pointer', ['compile', 'integer'], ['ref_bit_size...'])
def compile_integer_pointer(lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
    if len(args) == 1:
        bit_size = args[0].force_get_property('integer').associated_value
        if bit_size is None:
            return pwarning(f"Bit size for pointer must be known at compile time", anchor=args[0])
    elif len(args) == 0:
        bit_size = 64
    else:
        return pwarning(f"pointer definition takes at most one argument, got {len(args)}", anchor=lhs)
    
    raw_value = compile.get_compiled(lhs, scope)
    # llvm ir wants pointer type, so we cast the raw value to a pointer type
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    res = builder.inttoptr(raw_value, ir.PointerType(ir.IntType(bit_size)))
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
    pointer_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.replace_property('pointer', pointer_prop).replace_property('compiled_result', compiled_prop)

@register_definition('pointer', ['compile'], ['ref_bit_size...'])
def compile_pointer(lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
    if len(args) == 1:
        bit_size = args[0].force_get_property('integer').associated_value
        if bit_size is None:
            perror(f"Bit size for pointer must be known at compile time", anchor=args[0])
    elif len(args) == 0:
        bit_size = 64
    else:
        perror(f"pointer definition takes at most one argument, got {len(args)}", anchor=lhs)
    
    raw_value = compile.get_compiled(lhs, scope)
    # we cast a pointer to a pointer of a different size
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    res = builder.bitcast(raw_value, ir.PointerType(ir.IntType(bit_size)))
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
    pointer_prop = Property(lhs.symbol.create_renamed('pointer'))
    return Expression(lhs.symbol, properties=[pointer_prop, compiled_prop])  # We don't want to keep any types from the original expression

@register_definition('dereference', ['compile', 'pointer'])
def compile_dereference(lhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    res = builder.load(ptr_value)
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
    return lhs.replace_property('pointer', Property(lhs.symbol.create_renamed('integer'))).replace_property('compiled_result', compiled_prop)

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
        perror(f"Undefined variable '{name}'", anchor=lhs)
    var_ptr = compile.get_compiled(var, scope)
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=var_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compiled_prop)

@register_definition('allocate', ['compile'], [('count', ['integer'])])
def compile_allocate(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    count_value = compile.get_compiled(rhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')
    allocated_ptr = builder.call(module.get_global('malloc'), [count_value])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=allocated_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compiled_prop)

@register_definition('deallocate', ['compile', 'pointer'])
def compile_deallocate(lhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')
    builder.call(module.get_global('free'), [ptr_value])
    return lhs

@register_definition('reallocate', ['compile', 'pointer'], [('new_count', ['integer'])])
def compile_reallocate(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    new_count_value = compile.get_compiled(rhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')
    res_ptr = builder.call(module.get_global('realloc'), [ptr_value, new_count_value])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compiled_prop)

@register_definition('+', ['compile', 'pointer'], ['offset'])
def compile_pointer_advance(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    offset_value = compile.get_compiled(rhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    res_ptr = builder.gep(ptr_value, [offset_value])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compiled_prop)

@register_definition('-', ['compile', 'pointer'], ['offset'])
def compile_pointer_retreat(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    ptr_value = compile.get_compiled(lhs, scope)
    offset_value = compile.get_compiled(rhs, scope)
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    res_ptr = builder.gep(ptr_value, [builder.neg(offset_value)])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res_ptr)
    ptr_prop = Property(lhs.symbol.create_renamed('pointer'))
    return lhs.create_with_property(ptr_prop).replace_property('compiled_result', compiled_prop)