from typing import Callable, Collection

from constants import Property, Expression, Definition, Scope
import constants
from errors import perror, pwarning, ErrorMessage
from definitions import global_definitions, get_context, inherits, make_global_vars
from tokenizer import tokenize, build_tree

class UserDefinedDefinition(Definition):
    def apply(self, expr: Expression, args: list[Expression], scope: Scope, prop: Property) -> Expression:
        self.trace_stack.append((expr, args, scope, prop))    # for trace prints
        if len(self.params) > len(args):
            perror(ErrorMessage.BAD_NUMBER_ARGS, self.params, self, args, anchor=expr)
        for param, arg in zip(self.params, args):
            if not inherits(arg, param):
                perror(ErrorMessage.BAD_TYPE, arg, param, anchor=expr)
        
        new_scope = Scope(parent_scope=self.scope)
        new_scope.local_vars[self.prop_symb] = expr
        for arg, param in zip(args, self.params):
            new_scope.local_vars[param.symbol.s] = arg
        # We pass in any additional arguments via a special variable `arguments`
        additional_args = args[len(self.params):]
        list_prop = Property(expr.symbol.create_renamed('list'), is_association=True, associated_value=additional_args)
        new_scope.local_vars['arguments'] = Expression(expr.symbol.create_renamed('arguments'), properties=[list_prop])

        last = expr
        for local_expr in self.body:
            try:
                last = expression_resolve_all(local_expr, new_scope, constants.resolve)
            except Exception as e:
                perror("error while resolving {}", local_expr, anchor=local_expr, child_error=e)
        self.trace_stack.pop()
        return last


# Begin function definitions

def resolve_property_on(expr: Expression, prop: Property, scope: Scope, additional_compound: list[Expression]) -> Expression:
    '''
    resolves the property on the expression
    It is safe to call resolve_property_on when the property is known,
    but if evaluating code directly, resolve_last_property should be used

    additional_compound is used for `.(...)` resolution to pass the arguments
    '''
    # Combine with the additional properties
    prop = prop.copy()
    prop.compound_properties += additional_compound

    # Everything in context gets max weight
    context = get_context(scope)

    matches = scope.defn_lookup_recursive(prop.property.s)
    score, best_match = matches.lookup(expr.properties, context)
    if score < 0:
        return pwarning(f"Could not resolve property `{prop}` on `{expr}`", anchor=expr)
    elif best_match is None:
        return pwarning(f"Multiple matches found for property `{prop}` on `{expr}`", anchor=expr)
    # print(expr, '>>>', best_match)
    
    # forward resolve
    who_to_resolve = constants.immediate_resolve if prop.start_char == '{' else constants.resolve
    args = [expression_resolve_all(local_expr, scope, who_to_resolve) for local_expr in prop.compound_properties]

    # apply the best match
    res = best_match.apply(expr, args, scope, prop)
    return res

def resolve_last_property(expr: Expression, scope: Scope, additional_compound: list[Expression]) -> Expression:
    '''
    Resolves the last property of expr.
    It is safe to call resolve_property_on when the property is known,
    but if evaluating code directly, resolve_last_property should be used
    '''
    properties = expr.properties
    if len(properties) == 0:
        perror("cannot resolve property on expression with no properties", anchor=expr)
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

def run_file(file: str):
    built, i = build_tree(tokenize(file))
    builtin_scope = Scope(local_vars=make_global_vars(file), local_defns=global_definitions, is_global=True)
    scope = Scope(parent_scope=builtin_scope, is_global=True)
    for expr in built:
        expr = expression_resolve_all(expr, scope, constants.resolve)
    return scope

if __name__ == "__main__":
    from argparse import ArgumentParser
    argparser = ArgumentParser(description="Run a .lang file")
    argparser.add_argument('file', help='the .lang file to run')
    args = argparser.parse_args()
    file = args.file

    run_file(file)