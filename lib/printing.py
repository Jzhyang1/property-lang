if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token, expand_property
    from definitions import builtin_defn, binary_apply, pwarning, perror


@builtin_defn
class PrintIntegerDefinition(Definition):
    symbol = 'print'
    property_names = ['integer']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        ival = lhs.try_get_property('integer')
        assert ival is not None
        print(ival)
        return lhs

@builtin_defn
class PrintStringDefinition(Definition):
    symbol = 'print'
    property_names = ['string']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        sval = lhs.try_get_property('string')
        assert sval is not None
        print(sval.associated_value)
        return lhs