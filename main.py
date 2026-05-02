from typing import Callable, Collection

from constants import Property, Expression, Definition, Scope
import constants
from definitions import global_definitions, make_global_vars, pwarning, CompileError
from tokenizer import tokenize, build_tree

class UserDefinedDefinition(Definition):
    def apply(self, expr: Expression, args: list[Expression], scope: Scope, prop: Property) -> Expression:
        scope = scope.parent or scope
        new_varscope = {
            self.prop_symb: expr
        }
        for arg, param in zip(args, self.params):
            new_varscope[param.symbol.s] = arg
        new_scope = Scope(local_vars=new_varscope, parent_scope=scope)
        last = expr
        for local_expr in self.body:
            try:
                last = expression_resolve_all(local_expr, new_scope, constants.resolve)
            except Exception | AssertionError as e:
                raise CompileError(f"error while resolving {local_expr}", anchor=local_expr.symbol, child_error=e)
        return last


# Begin function definitions

def resolve_property_on(expr: Expression, prop: Property, scope: Scope, additional_compound: list[Expression]) -> Expression:
    '''
    resolves the property on the expression
    It is safe to call resolve_property_on when the property is known,
    but if evaluating code directly, resolve_last_property should be used

    additional_compound is used for `.(...)` resolution to pass the arguments
    '''
    property_set: set[str] = set(p.property.s for p in expr.properties)
    # Combine with the additional properties
    prop = prop.copy()
    prop.compound_properties += additional_compound

    print("Resolving", prop, "on", expr)

    matches = scope.defn_lookup(prop.property.s)
    if matches is None:
        pwarning(f"no matches found for property {prop} in symbol {expr.symbol}", anchor=prop.property)
        return expr
    
    # TODO filter out compound properties to those that match the properties of expr
    matches = [m for m in matches if all(p.property.s in property_set for p in m.properties)] # filter for matches that have all the other properties
    if len(matches) == 0:
        pwarning(f"no matches found for property {prop} in symbol {expr.symbol} with properties {property_set}", anchor=prop.property)
        return expr
    
    # if there are multiple matches choose the one that has the last property of properties
    #  then the second to last, etc. until we find a unique match or run out of properties/matches
    matches_sets = [(set(p.property.s for p in m.properties), m) for m in matches]
    for p in reversed(expr.properties):
        if len(matches_sets) <= 1:
            break
        matches_sets = [(ps, m) for ps, m in matches_sets if p.property.s in ps]
    # if there are multiple matches with the same number of properties, print an error
    #  we know this happened if len(matches_sets) == 0 since that means we discarded multiple matches at the same time
    if len(matches_sets) == 0:
        raise CompileError(f"multiple matches found for property {prop} in symbol {expr.symbol} with properties {property_set}", anchor=prop.property)
    _, best_match = matches_sets[-1]
    
    # forward resolve
    who_to_resolve = constants.immediate_resolve if prop.start_char == '{' else constants.resolve
    args = [expression_resolve_all(local_expr, scope, who_to_resolve) for local_expr in prop.compound_properties]

    # apply the best match
    return best_match.apply(expr, args, scope, prop)

def resolve_last_property(expr: Expression, scope: Scope, additional_compound: list[Expression]) -> Expression:
    '''
    Resolves the last property of expr.
    It is safe to call resolve_property_on when the property is known,
    but if evaluating code directly, resolve_last_property should be used
    '''
    properties = expr.properties
    if len(properties) == 0:
        raise CompileError("cannot resolve property on expression with no properties", anchor=expr.symbol)
    *properties, prop = properties
    if prop in constants.resolve:
        # Go one level down
        expr = resolve_last_property(Expression(expr.symbol, properties), scope, prop.compound_properties)
    return resolve_property_on(Expression(expr.symbol, properties), prop, scope, additional_compound)

def expression_resolve_all(expr: Expression, scope: Scope, resolve_these: Collection[str]) -> Expression:
    '''
    Resolves all properties marked for resolution in expr.
    '''
    expr_copy = Expression(expr.symbol, [])
    for prop in expr.properties:
        if prop.is_compound:
            prop = prop.copy()
            prop.compound_properties = [expression_resolve_all(p, scope, constants.immediate_resolve) for p in prop.compound_properties]

        if prop.property.s in resolve_these:
            expr_copy = resolve_last_property(expr_copy, scope, prop.compound_properties)
            expr_copy = Expression(expr_copy.symbol, expr_copy.properties.copy())
            assert not any(p.property.s in resolve_these for p in expr_copy.properties)
        else:
            expr_copy.properties.append(prop)
    return expr_copy

if __name__ == "__main__":
    from argparse import ArgumentParser
    argparser = ArgumentParser(description="Run a .lang file")
    argparser.add_argument('file', help='the .lang file to run')
    args = argparser.parse_args()
    file = args.file

    built, i = build_tree(tokenize(file))
    scope = Scope(local_vars=make_global_vars(file), local_defns=global_definitions)
    for expr in built:
        expr = expression_resolve_all(expr, scope, constants.resolve)
        # expr = expression_resolve_all(expr, scope)