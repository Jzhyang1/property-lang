from constants import Definition, Provenance, Scope, Expression, Property, Token
from errors import pwarning
from definitions import register_definition, create_list
import definitions
compile = definitions.import_module(Provenance.here(), 'compile.py')

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
        return pwarning(f'Index out of bounds: {rval.associated_value}', anchor=rhs)
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
    prop, defn = rhs.force_get_property('property').associated_value
    from main import resolve_last_property
    res: list[Expression] = []
    for item in iterable.associated_value:
        # item is an Expression
        res.append(defn.apply(item, [], scope, prop))
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
# Find compilation under compile.py and lib/list.lang