from constants import Property, Expression, Definition, Scope
from definitions import global_definitions, make_global_vars, pwarning, CompileError
from tokenizer import tokenize, build_tree

class UserDefinedDefinition(Definition):
    def apply(self, expr: Expression, args: list[Expression], scope: Scope, prop: Property) -> Expression:
        scope = scope.parent or scope
        new_varscope = {
            self.placeholder_symb: expr
        }
        for arg, param in zip(args, self.params):
            new_varscope[param.symbol.s] = arg
        new_scope = Scope(local_vars=new_varscope, parent_scope=scope)
        last = expr
        for local_expr in self.body:
            local_expr = resolve_vars(local_expr, new_scope) # we need to resolve the variable into values
            last = resolve_last_property(local_expr, new_scope)
        return last


# Begin function definitions

def resolve_vars(expr: Expression, scope: Scope) -> Expression:
    '''
    Resolves the expression's identifier property recursively within all properties.
    Returns the expression with all before the identifier property replaced with the resolved expression
    * this is a single-pass resolution, so any identifier properties introduced by resolution will not be resolved
    '''
    properties = [
        Property(p.property, True, [resolve_vars(e, scope) for e in p.compound_properties], p.is_association, p.associated_value, p.start_char) 
        if p.is_compound else p for p in expr.properties
    ]
    expr = Expression(expr.symbol, properties)
    var_expr, remaining_properties = expr.pop_properties_after('identifier')
    if remaining_properties is None:
        # Not an identifier
        return expr
    # Resolve the identifier if the variable exists
    if scope.var_lookup(var_expr.symbol.s) is None:
        pwarning(f"variable {var_expr.symbol.s} not found in scope", anchor=var_expr.symbol)
        return expr
    res = resolve_last_property(var_expr, scope)
    return Expression(res.symbol, res.properties + remaining_properties)

def resolve_property_on(expr: Expression, prop: Property, scope: Scope) -> Expression:
    '''
    resolves the property on the expression
    It is safe to call resolve_property_on when the property is known,
    but if evaluating code directly, resolve_last_property should be used
    '''
    # TODO refactor resolve_last_property to call resolve_property_on
    return resolve_last_property(expr.create_with_property(prop), scope)

def resolve_last_property(expr: Expression, scope: Scope) -> Expression:
    '''
    Resolves the last property of expr.
    It is safe to call resolve_property_on when the property is known,
    but if evaluating code directly, resolve_last_property should be used
    '''
    properties = expr.properties
    while len(properties) > 0 and properties[-1].property.s in [',']:
        properties = properties[:-1]
    if len(properties) == 0:
        raise CompileError("cannot resolve property on expression with no properties", anchor=expr.symbol)
        pwarning(f"no properties to resolve for {expr}")
        return expr
    *properties, prop = properties

    # We need to handle backward resolution
    if len(properties) > 0 and properties[-1].property.s in ['.', ';']:
        pwarning("Something went terribly wrong")
        expr = resolve_last_property(Expression(expr.symbol, properties[:-1]), scope)
        properties = expr.properties.copy()
    if prop.property.s in ['.', ';']:
        expr = resolve_last_property(Expression(expr.symbol, properties), scope)
        *properties, prop = expr.properties

    property_set: set[str] = set(p.property.s for p in properties)

    matches = scope.defn_lookup(prop.property.s)
    if matches is None:
        pwarning(f"no matches found for property {prop} in symbol {expr.symbol}", anchor=prop.property)
        return expr
    
    if prop.is_compound: # is compound
        matches = [m for m in matches if m.is_compound] # filter for compound matches
    else:
        matches = [m for m in matches if not m.is_compound] # filter for non-compound matches
    matches = [m for m in matches if all(p.property.s in property_set for p in m.properties)] # filter for matches that have all the other properties
    if len(matches) == 0:
        pwarning(f"no matches found for property {prop} in symbol {expr.symbol} with properties {property_set}", anchor=prop.property)
        return expr
    
    # if there are multiple matches choose the one that has the last property of properties
    #  then the second to last, etc. until we find a unique match or run out of properties/matches
    matches_sets = [(set(p.property.s for p in m.properties), m) for m in matches]
    for p in reversed(properties):
        if len(matches_sets) <= 1:
            break
        matches_sets = [(ps, m) for ps, m in matches_sets if p.property.s in ps]
    # if there are multiple matches with the same number of properties, print an error
    #  we know this happened if len(matches_sets) == 0 since that means we discarded multiple matches at the same time
    if len(matches_sets) == 0:
        pwarning(f"multiple matches found for property {prop} in symbol {expr.symbol} with properties {property_set}")
        return expr
    _, best_match = matches_sets[0]
    
    # forward resolve
    args = [resolve_expression(local_expr, scope) for local_expr in prop.compound_properties]

    # apply the best match
    return best_match.apply(
        Expression(expr.symbol, properties), 
        args, scope, prop
    )

def resolve_expression(expr: Expression, scope: Scope) -> Expression:
    '''
    resolves all properties marked for resolution in expr
    '''
    expr_copy = Expression(expr.symbol, [])
    for prop in expr.properties:
        if prop.property.s in ['.', ';']:
            expr_copy = resolve_last_property(expr_copy, scope)
            expr_copy = Expression(expr_copy.symbol, expr_copy.properties.copy())
            assert not any(p.property.s in ['.', ';'] for p in expr_copy.properties)
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
        resolve_expression(expr, scope)