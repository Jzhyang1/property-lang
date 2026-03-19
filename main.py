from constants import Property, Expression, Definition, Scope
from definitions import global_definitions, pwarning, builtin_definition, binary_apply
from tokenizer import tokenize, build_tree

class UserDefinedDefinition(Definition):
    def apply(self, expr: Expression, args: list[Expression], scope: 'Scope') -> Expression:
        new_varscope = {
            self.placeholder_symb: expr
        }
        for arg, param in zip(args, self.params):
            new_varscope[param.symbol.s] = arg
        new_scope = Scope(local_vars=new_varscope, parent_scope=scope)
        return resolve_expr(self.body, new_scope)


# Begin function definitions


def resolve_vars(property: Property, scope: Scope, nested=False) -> Property:
    '''
    resolves the property's variables if it is compound, otherwise returns the property
    '''
    if not property.is_compound:
        return property
    if not (nested or property.start_char in ['{', '[']):
        return property

    property = property.copy()
    expressions : list[Expression] = []
    for expr in property.compound_properties:
        expr = Expression(expr.symbol, expr.properties.copy())
        if (var := scope.var_lookup(expr.symbol.s)) is not None:
            expr.symbol = var.symbol
            expr.properties = var.properties + expr.properties
        # resolve recursively
        for i in reversed(range(len(expr.properties))):
            expr.properties[i] = resolve_vars(expr.properties[i], scope, True)
        expressions.append(expr)
    property.compound_properties = expressions
    return property

def resolve_expr(expr: Expression, scope: Scope) -> Expression:
    '''
    resolves the last property of expr
    '''
    if len(expr.properties) == 0:
        return expr
    properties = expr.properties.copy()

    # if prop is '.' we resolve with indirection
    # if prop is ';' or ',' we ignore the symbol
    prop = properties.pop()
    while len(properties) > 0 and prop.property.s in [';', ',']:
        prop = properties.pop()
    if prop.property == '.':
        return resolve_expr(Expression(expr.symbol, properties), scope)
    if len(properties) > 0 and properties[-1].property == '.':
        expr = resolve_expr(Expression(expr.symbol, properties[:-1]), scope)
        properties = expr.properties
    prop = resolve_vars(prop, scope)
    property_set: set[str] = set(p.property.s for p in properties)

    matches = scope.defn_lookup(prop.property.s)
    if matches is None:
        pwarning(f"no matches found for property {prop} in symbol {expr.symbol}")
        return expr
    
    if prop.is_compound: # is compound
        matches = [m for m in matches if m.is_compound] # filter for compound matches
    else:
        matches = [m for m in matches if not m.is_compound] # filter for non-compound matches
    matches = [m for m in matches if all(p.property.s in property_set for p in m.properties)] # filter for matches that have all the other properties
    if len(matches) == 0:
        pwarning(f"no matches found for property {prop} in symbol {expr.symbol} with properties {property_set}")
        return expr
    
    # find the match with the most properties
    matches.sort(key=lambda m: len(m.properties), reverse=True)
    # if there are multiple matches with the same number of properties, print an error
    if len(matches) > 1 and len(matches[0].properties) == len(matches[1].properties):
        pwarning(f"multiple matches found for property {prop} in symbol {expr.symbol} with properties {property_set}")
        return expr
    
    if prop.start_char == '{':
        # resolve all
        args = [resolve_expr(local_expr, scope) for local_expr in prop.compound_properties]
    else:
        # resolve all that end in '.' or ';'
        args = []
        for local_expr in prop.compound_properties:
            if local_expr.properties[-1].property.s in ['.', ';']:
                local_expr = Expression(local_expr.symbol, local_expr.properties[:-1])
                args.append(resolve_expr(local_expr, scope))
            else:
                args.append(local_expr)

    # apply the best match
    best_match = matches[0]
    return best_match.apply(
        Expression(expr.symbol, properties), 
        args, scope
    )

if __name__ == "__main__":
    from argparse import ArgumentParser
    argparser = ArgumentParser(description="Run a .lang file")
    argparser.add_argument('file', help='the .lang file to run')
    args = argparser.parse_args()
    file = args.file

    tokenize(file)
    built, i = build_tree(tokenize(file))
    scope = Scope(local_defns=global_definitions)
    for expr in built:
        if expr.properties[-1].property.s in ['.', ';']:
            expr = Expression(expr.symbol, expr.properties[:-1])
            resolve_expr(expr, scope)