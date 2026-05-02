if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, binary_apply, multi_apply, pwarning, CompileError


@builtin_definition
class StringEqualDefinition(Definition):
    symbol = '=='
    param_names = ['rhs']
    property_names = ['string']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.force_get_property('string')
        rval = rhs.force_get_property('string')
        res = lval.associated_value == rval.associated_value
        return Expression(lhs.symbol.create_renamed('=='), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
        ])

@builtin_definition
class StringNotEqualDefinition(Definition):
    symbol = '!='
    param_names = ['rhs']
    property_names = ['string']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.force_get_property('string')
        rval = rhs.force_get_property('string')
        res = lval.associated_value != rval.associated_value
        return Expression(lhs.symbol.create_renamed('!='), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
        ])

@builtin_definition
class StringConcatDefinition(Definition):
    symbol = '+'
    property_names = ['string']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.force_get_property('string')
        rval = rhs.force_get_property('string')
        return Expression(lhs.symbol.create_renamed('+'), [
            Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=lval.associated_value + rval.associated_value)
        ])
    
@builtin_definition
class StringSplitDefinition(Definition):
    symbol = 'split'
    property_names = ['string']
    param_names = ['delimiters...'] # not included in the result
    @multi_apply
    def apply(self, lhs: Expression, rhs: list[Expression], scope: Scope) -> Expression:
        lval = lhs.force_get_property('string')
        delimiters = []
        for r in rhs:
            delimiters.append(r.force_get_property('string').associated_value)
        res = [lval.associated_value]
        for d in delimiters:
            new_res = []
            for s in res:
                new_res.extend(s.split(d))
            res = new_res
        return Expression(lhs.symbol.create_renamed('split'), [
            Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=res)
        ])