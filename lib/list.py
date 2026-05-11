if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, binary_apply, multi_apply, create_list, CompileError

# We extend compilation
import llvmlite.ir as ir

from constants import Expression, Property, Scope
if 'definitions' in globals():
    compile = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'compile.py')
else:
    raise ImportError("definitions module not found, cannot import compile module")


@builtin_definition
class ListDefinition(Definition):
    symbol = 'list'
    param_names = ['items...']
    @multi_apply
    def apply(self, lhs: Expression, items: list[Expression], scope: Scope) -> Expression:
        prop = Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=items)
        return lhs.create_with_property(prop)

@builtin_definition
class ListAppendDefinition(Definition):
    symbol = 'append'
    property_names = ['list']
    param_names = ['item']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        dst = lhs.try_get_property('list')
        assert dst is not None
        dst.is_association = True
        dst.associated_value = dst.associated_value or []
        dst.associated_value.append(rhs)
        return rhs
    
@builtin_definition
class ListAtDefinition(Definition):
    symbol = 'at'
    param_names = ['idx']
    property_names = ['list']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.try_get_property('list')
        rval = rhs.try_get_property('integer')
        assert lval is not None and rval is not None
        res = lval.associated_value[rval.associated_value]
        return res

@builtin_definition
class ListConcatDefinition(Definition):
    symbol = '+'
    property_names = ['list']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.try_get_property('list')
        rval = rhs.try_get_property('list')
        assert lval is not None and rval is not None
        res = lval.associated_value + rval.associated_value
        return Expression(lhs.symbol.create_renamed('+'), [
            Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=res)
        ])
    
@builtin_definition
class ListEachDefinition(Definition):
    symbol = 'each'
    property_names = ['list']
    param_names = ['callback_property']
    @binary_apply
    def apply(self, lhs: Expression, callback: Expression, scope: Scope) -> Expression:
        iterable = lhs.try_get_property('list')
        assert iterable is not None 
        if iterable.associated_value is None:
            return lhs
        if (pval := callback.try_get_property('property')) is None:
            raise CompileError(f'`each` requires a property argument, got {callback}')
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

@builtin_definition
class ListEqualDefinition(Definition):
    symbol = '=='
    param_names = ['rhs']
    property_names = ['list']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.try_get_property('list')
        rval = rhs.try_get_property('list')
        assert lval is not None and rval is not None
        res = lval.associated_value == rval.associated_value
        return Expression(lhs.symbol.create_renamed('=='), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
        ])
    
# Compilation

# Lists are implemented as a structure { size, items... }
# The pointer passed around is to the first item. 
# Size can be retrieved by looking at pointer - 1.
# All items are qwords

def round_up_to_power_of_2(n: int) -> int:
    hob = (-n) & n  # Get the highest order bit
    if hob == n:
        return n
    return hob << 1

def compile_get_list_size_and_pointer(list_ptr, builder):
    # list_ptr is an integer, so we cast it
    list_ptr = builder.inttoptr(list_ptr, ir.PointerType(ir.IntType(64)))
    size_ptr = builder.gep(list_ptr, [ir.Constant(ir.IntType(64), -1)])  # Move back one qword to get size
    size = builder.load(size_ptr)
    return size, size_ptr

@builtin_definition
class CompileListDefinition(Definition):
    symbol = 'compile'
    property_names = ['list']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, rprops = lhs.discard_properties_after('list')
        element_count = len(rprops.compound_properties)
        real_size = round_up_to_power_of_2(element_count + 1) * 8   # 1 qword for size, rest for items
        # Allocate memory for the list
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        module = compile.get_compile_construct(scope, '__MODULE__')
        malloc = module.get_global('malloc')
        ptr = builder.call(malloc, [ir.Constant(ir.IntType(64), real_size)])
        ptr = builder.bitcast(ptr, ir.PointerType(ir.IntType(64)))  # Cast to pointer to qword
        # Store the size at ptr - 8
        builder.store(ir.Constant(ir.IntType(64), element_count), ptr)
        res_ptr = builder.ptrtoint(ptr, ir.IntType(64))
        res_ptr = builder.add(res_ptr, ir.Constant(ir.IntType(64), 8))  # Move past size
        items_ptr = builder.inttoptr(res_ptr, ir.PointerType(ir.IntType(64)))
        # Store the items
        for i, prop in enumerate(rprops.compound_properties):
            item_val = compile.get_compiled(prop, scope)
            item_ptr = builder.gep(items_ptr, [ir.Constant(ir.IntType(64), i)])
            builder.store(item_val, item_ptr)
        # Keep the list property for typing
        return lhs.create_with_property(rprops).replace_property('compile', Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res_ptr))

@builtin_definition
class CompileListAppendDefinition(Definition):
    symbol = 'compile'
    property_names = ['list', 'append']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        list_prop = lhs.try_get_property('list')
        assert list_prop is not None
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        module = compile.get_compile_construct(scope, '__MODULE__')
        list_ptr = compile.get_compiled(lhs, scope)
        old_size, old_size_ptr = compile_get_list_size_and_pointer(list_ptr, builder)
        new_size = builder.add(old_size, ir.Constant(ir.IntType(64), 1))
        builder.store(new_size, old_size_ptr)  # Update size

        # Compute resize condition
        new_size_plus_one = builder.add(new_size, ir.Constant(ir.IntType(64), 1))
        bit_check = builder.and_(new_size, new_size_plus_one)
        needs_resize = builder.icmp_unsigned('==', bit_check, ir.Constant(ir.IntType(64), 0))

        # Prepare blocks
        current_block = builder.block
        resize_block = builder.append_basic_block('resize')
        no_resize_block = builder.append_basic_block('no_resize')
        merge_block = builder.append_basic_block('merge')

        # Conditional branch
        builder.cbranch(needs_resize, resize_block, no_resize_block)

        # Resize block
        builder.position_at_start(resize_block)
        new_real_size = builder.mul(builder.add(new_size_plus_one, ir.Constant(ir.IntType(64), 1)), ir.Constant(ir.IntType(64), 8))
        realloc = module.get_global('realloc')
        new_size_ptr = builder.call(realloc, [builder.bitcast(old_size_ptr, ir.PointerType(ir.IntType(8))), new_real_size])
        new_size_ptr = builder.bitcast(new_size_ptr, ir.PointerType(ir.IntType(64)))
        builder.store(new_size, new_size_ptr)  # Update size
        new_list_ptr = builder.gep(new_size_ptr, [ir.Constant(ir.IntType(64), 1)])  # Move past size qword to get new list pointer
        resized_ptr = builder.ptrtoint(new_list_ptr, ir.IntType(64))
        builder.branch(merge_block)

        # No-resize block
        builder.position_at_start(no_resize_block)
        builder.branch(merge_block)

        # Merge block
        builder.position_at_start(merge_block)
        phi = builder.phi(ir.IntType(64))
        phi.add_incoming(resized_ptr, resize_block)
        phi.add_incoming(list_ptr, no_resize_block)

        # Store the new item
        resized_list_ptr_ptr = builder.inttoptr(phi, ir.PointerType(ir.IntType(64)))
        item_ptr = builder.gep(resized_list_ptr_ptr, [new_size])
        item_val = compile.get_compiled(lhs, scope)
        builder.store(item_val, item_ptr)

        # Return the updated list pointer
        return lhs.replace_property('compile', Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=phi))
    
@builtin_definition
class CompileListAtDefinition(Definition):
    symbol = 'compile'
    property_names = ['list', 'at']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, rprops = lhs.discard_properties_after('at')
        # print("lhs", lhs, "rprops", rprops)
        if len(rprops.compound_properties) != 1:
            raise CompileError("expected exactly one property after 'at' for list indexing", anchor=rprops.property)
        idx_val = compile.get_compiled(rprops.compound_properties[0], scope)
        lhs_val = compile.get_compiled(lhs, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        # Get the pointer to the first item
        items_ptr = builder.inttoptr(lhs_val, ir.PointerType(ir.IntType(64)))
        # Get the item at index idx_val
        item_ptr = builder.gep(items_ptr, [idx_val])
        item_val = builder.load(item_ptr)
        return lhs\
            .replace_property('list', Property(lhs.symbol.create_renamed('integer')))\
            .replace_property('compile', Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=item_val))
    