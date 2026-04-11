if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, pwarning, CompileError


@builtin_definition
class PrintIntegerDefinition(Definition):
    symbol = 'print'
    property_names = ['integer']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        ival = lhs.try_get_property('integer')
        assert ival is not None
        print(ival.associated_value)
        return lhs

@builtin_definition
class PrintStringDefinition(Definition):
    symbol = 'print'
    property_names = ['string']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        sval = lhs.try_get_property('string')
        assert sval is not None
        print(sval.associated_value)
        return lhs
    
@builtin_definition
class PrintListDefinition(Definition):
    symbol = 'print'
    property_names = ['list']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        sval = lhs.try_get_property('list')
        assert sval is not None
        print(sval.associated_value)
        return lhs