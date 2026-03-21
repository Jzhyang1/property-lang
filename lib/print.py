if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, binary_apply, pwarning, CompileError


@builtin_definition
class PrintIntegerDefinition(Definition):
    symbol = 'print'
    property_names = ['integer']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        ival = lhs.try_get_property('integer')
        assert ival is not None
        print(ival)
        return lhs

@builtin_definition
class PrintStringDefinition(Definition):
    symbol = 'print'
    property_names = ['string']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        sval = lhs.try_get_property('string')
        assert sval is not None
        print(sval.associated_value)
        return lhs
    
@builtin_definition
class PrintListDefinition(Definition):
    symbol = 'print'
    property_names = ['list']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        sval = lhs.try_get_property('list')
        assert sval is not None
        print(sval.associated_value)
        return lhs