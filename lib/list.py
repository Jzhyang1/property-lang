if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, binary_apply, multi_apply, create_list, CompileError


@builtin_definition
class ListDefinition(Definition):
    symbol = 'list'
    param_names = ['items...']
    @multi_apply
    def apply(self, lhs: Expression, items: list[Expression], scope: Scope) -> Expression:
        prop = Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=items)
        props = lhs.properties + [prop]
        return Expression(lhs.symbol, props)

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