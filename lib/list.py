if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, binary_apply, pwarning, CompileError


@ builtin_definition
class ListDefinition(Definition):
    symbol = 'list'
    param_names = ['items...']
    def apply(self, lhs: Expression, items: list[Expression], scope: Scope) -> Expression:
        prop = Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=items)
        props = lhs.properties + [prop]
        return Expression(lhs.symbol, props)

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