if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, binary_apply, pwarning, perror


@builtin_definition
class StringEqualDefinition(Definition):
    symbol = '=='
    property_names = ['string']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.try_get_property('string')
        rval = rhs.try_get_property('string')
        assert lval is not None and rval is not None
        res = lval.associated_value == rval.associated_value
        return Expression(lhs.symbol.create_renamed('=='), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
        ])

@builtin_definition
class StringConcatDefinition(Definition):
    symbol = '+'
    property_names = ['string']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.try_get_property('string')
        rval = rhs.try_get_property('string')
        assert lval is not None and rval is not None
        return Expression(lhs.symbol.create_renamed('+'), [
            Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=lval.associated_value + rval.associated_value)
        ])