from constants import Definition, Scope, Expression, Property, Token
from definitions import register_definition, create_list, CompileError
import definitions
# We extend compilation
import llvmlite.ir as ir
import llvmlite.binding as llvm
compile = definitions.import_module(__file__, 'compile.py')

# A sequential collection of heterogeneous elements

@register_definition('list', [], ['items...'])
def list_(lhs: Expression, args: list[Expression]) -> Expression:
    prop = Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=args)
    return lhs.create_with_property(prop)

@register_definition('append', ['list'], ['item'])
def append(lhs: Expression, rhs: Expression) -> Expression:
    dst = lhs.force_get_property('list')
    dst.is_association = True
    dst.associated_value = dst.associated_value or []
    dst.associated_value.append(rhs)
    return lhs

@register_definition('at', ['list'], ['idx'])
def at(lhs: Expression, rhs: Expression) -> Expression:
    lval = lhs.force_get_property('list')
    rval = rhs.force_get_property('integer')
    if 0 <= rval.associated_value < len(lval.associated_value):
        res = lval.associated_value[rval.associated_value]
    else:
        raise CompileError(f'Index out of bounds: {rval.associated_value}', anchor=rhs.symbol)
    return res

@register_definition('+', ['list'], ['list_operand'])
def concat(lhs: Expression, rhs: Expression) -> Expression:
    lval = lhs.force_get_property('list')
    rval = rhs.force_get_property('list')
    res = lval.associated_value + rval.associated_value
    return Expression(lhs.symbol.create_renamed('+'), [
        Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=res)
    ])

@register_definition('each', ['list'], ['callback_operand'])
def each(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    iterable = lhs.try_get_property('list')
    assert iterable is not None 
    if iterable.associated_value is None:
        return lhs
    if (pval := rhs.try_get_property('property')) is None:
        raise CompileError(f'`each` requires a property argument, got {rhs}')
    prop = pval.associated_value
    assert prop is not None
    from main import resolve_last_property
    res: list[Expression] = []
    for item in iterable.associated_value:
        # item is an Expression
        expr = Expression(item.symbol, 
                          item.properties + [prop])
        res.append(resolve_last_property(expr, scope, []))
    return create_list(lhs.symbol, res)

@register_definition('==', ['list'], ['list_operand'])
def equal(lhs: Expression, rhs: Expression) -> Expression:
    lval = lhs.force_get_property('list')
    rval = rhs.force_get_property('list')
    res = lval.associated_value == rval.associated_value
    return Expression(lhs.symbol.create_renamed('=='), [
        Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
    ])

@register_definition('!=', ['list'], ['list_operand'])
def not_equal(lhs: Expression, rhs: Expression) -> Expression:
    lval = lhs.force_get_property('list')
    rval = rhs.force_get_property('list')
    res = lval.associated_value != rval.associated_value
    return Expression(lhs.symbol.create_renamed('!='), [
        Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
    ])

@register_definition('length', ['list'], [])
def length(lhs: Expression) -> Expression:
    lval = lhs.force_get_property('list')
    res = len(lval.associated_value) if lval.associated_value is not None else 0
    return Expression(lhs.symbol.create_renamed('length'), [
        Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
    ])
    
# Compilation

# This file only implements `compile list(...)`, the rest are implemented in `list.lang`
# A list is implemented as a contiguous memory with a size header for each item
# followed by the item data. After the last item is a terminating 64-bit size = 0
# <64-bit size> <item of size> <64-bit size> <item of size> ... <64-bit size = 0>
@register_definition('list', ['compile'], ['items...'])
def compile_list(lhs: Expression, args: list[Expression], scope: Scope, prop: Property) -> Expression:
    builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
    module: ir.Module = compile.get_compile_construct(scope, '__MODULE__')

    item_sizes = []
    int_size = 8
    total_size = int_size * (len(args) + 1) # +1 for the terminating 0 size
    for arg in args:
        arg_type: ir.Type = compile.get_type(arg, scope)
        arg_size = compile.size_of_type(arg_type) # TODO make sure that this works with alignment
        total_size += arg_size
        item_sizes.append((arg_type, arg_size))
    
    output_ptr = builder.call(module.get_global('malloc'), [ir.Constant(ir.IntType(64), total_size)], 'malloc_tmp')
    current_ptr = output_ptr
    for arg, (arg_type, arg_size) in zip(args, item_sizes):
        builder.store(ir.Constant(ir.IntType(64), arg_size), builder.bitcast(current_ptr, ir.PointerType(ir.IntType(64))))
        current_ptr = builder.gep(current_ptr, [ir.Constant(ir.IntType(64), int_size)])
        arg_val = compile.get_compiled(arg, scope)
        builder.store(arg_val, builder.bitcast(current_ptr, ir.PointerType(arg_type)))
        current_ptr = builder.gep(current_ptr, [ir.Constant(ir.IntType(64), arg_size)])
    builder.store(ir.Constant(ir.IntType(64), 0), builder.bitcast(current_ptr, ir.PointerType(ir.IntType(64))))
    
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=output_ptr)
    return lhs.create_with_property(prop).replace_property('compiled_result', compile_prop)

@register_definition('list', ['compile', 'pointer'])
def compile_list_from_pointer(lhs: Expression, scope: Scope, prop: Property) -> Expression:
    builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
    ptr_value = compile.get_compiled(lhs, scope)
    # Cast to pointer to int8
    ptr_value = builder.bitcast(ptr_value, ir.PointerType(ir.IntType(8)))
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=ptr_value)
    return lhs.replace_property('pointer', prop).replace_property('compiled_result', compile_prop)