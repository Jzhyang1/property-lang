if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, binary_apply, pwarning, CompileError, associated_value_to_expression

@builtin_definition
class ArithmeticAddDefinition(Definition):
    symbol = '+'
    param_names = ['operand']
    property_names = ['integer']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (ival := rhs.try_get_property('integer')) is None or \
            (idst := lhs.try_get_property('integer')) is None:
            raise CompileError(f"unable to add {rhs} to {lhs}")
        ires = idst.copy()
        ires.is_association = True
        ires.associated_value += ival.associated_value
        res_properties = [
            ires if property == idst else property for property in lhs.properties
        ]
        return Expression(lhs.symbol.create_renamed('+'), res_properties)

@builtin_definition
class ArithmeticSubtractDefinition(Definition):
    symbol = '-'
    param_names = ['operand']
    property_names = ['integer']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (ival := rhs.try_get_property('integer')) is None or \
            (idst := lhs.try_get_property('integer')) is None:
            raise CompileError(f"unable to subtract {rhs} from {lhs}")
        ires = idst.copy()
        ires.is_association = True
        ires.associated_value -= ival.associated_value
        res_properties = [
            ires if property == idst else property for property in lhs.properties
        ]
        return Expression(lhs.symbol.create_renamed('+'), res_properties)

@builtin_definition
class ArithmeticMultiplyDefinition(Definition):
    symbol = '*'
    param_names = ['operand']
    property_names = ['integer']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (ival := rhs.try_get_property('integer')) is None or \
            (idst := lhs.try_get_property('integer')) is None:
            raise CompileError(f"unable to multiply {rhs} to {lhs}")
        ires = idst.copy()
        ires.is_association = True
        ires.associated_value *= ival.associated_value
        res_properties = [
            ires if property == idst else property for property in lhs.properties
        ]
        return Expression(lhs.symbol.create_renamed('+'), res_properties)

@builtin_definition
class ArithmeticDivideDefinition(Definition):
    symbol = '/'
    param_names = ['operand']
    property_names = ['integer']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (ival := rhs.try_get_property('integer')) is None or \
            (idst := lhs.try_get_property('integer')) is None:
            raise CompileError(f"unable to divide {rhs} from {lhs}")
        if ival.associated_value == 0:
            raise CompileError(f"dividing by 0 in {lhs}/{rhs}")
        ires = idst.copy()
        ires.is_association = True
        ires.associated_value //= ival.associated_value
        res_properties = [
            ires if property == idst else property for property in lhs.properties
        ]
        return Expression(lhs.symbol.create_renamed('+'), res_properties)

@builtin_definition
class ArithmeticEqualDefinition(Definition):
    symbol = '=='
    param_names = ['operand']
    property_names = ['integer']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.try_get_property('integer')
        rval = rhs.try_get_property('integer')
        assert lval is not None and rval is not None
        res = lval.associated_value == rval.associated_value
        return associated_value_to_expression(lhs.symbol, res, '==')

@builtin_definition
class ArithmeticLessThanDefinition(Definition):
    symbol = '<'
    param_names = ['operand']
    property_names = ['integer']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (ival := rhs.try_get_property('integer')) is None or \
            (idst := lhs.try_get_property('integer')) is None:
            raise CompileError(f"unable to check {rhs} < {lhs}")
        res = idst.associated_value < ival.associated_value
        return associated_value_to_expression(lhs.symbol, res, '<')
