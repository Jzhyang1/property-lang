import inspect
from typing import Any, Callable
from errors import perror, pwarning, ErrorMessage

from constants import Definition, ExpressionLiteral, PropertyLiteral, Provenance, ProvenanceAware, Scope, Expression, Property, Token, literal_pack_to_expression, literal_pack_to_property, token_types
import constants

__LANG__ = '0.0.3'
global_definitions: dict[str, list[Definition]] = {}

def make_global_vars(file: str) -> dict[str, Expression]:
    file_token = Token('__IMPORT_PATH__', file, 0, 0, token_types['alnum'])
    string_token = Token('string', file, 0, 0, token_types['alnum'])
    global_vars = {
        '__IMPORT_PATH__': Expression(
            file_token,
            [Property(string_token, is_association=True, associated_value=file)]
        )
    }
    return global_vars

def expression_to_associated_value(expr: Expression) -> int | str | list:
    if (ival := expr.try_get_property('integer')) is not None:
        return ival.associated_value
    elif (sval := expr.try_get_property('string')) is not None:
        return sval.associated_value
    elif (lval := expr.try_get_property('list')) is not None and lval.associated_value is not None:
        return [expression_to_associated_value(e) for e in lval.associated_value]
    else:
        perror(f"unable to convert {expr} to associated value", anchor=expr)

def associated_value_to_expression(anchor: Token, value: Any, name:'str|None'=None) -> Expression:
    if isinstance(value, int):
        return Expression(anchor.create_renamed(name or 'integer'), [
            Property(anchor.create_renamed('integer'), is_association=True, associated_value=value)
        ])
    elif isinstance(value, bool):
        return Expression(anchor.create_renamed(name or 'integer'), [
            Property(anchor.create_renamed('integer'), is_association=True, associated_value=int(value))
        ])
    elif isinstance(value, str):
        return Expression(anchor.create_renamed(name or 'string'), [
            Property(anchor.create_renamed('string'), is_association=True, associated_value=value)
        ])
    elif isinstance(value, list):
        return Expression(anchor.create_renamed(name or 'list'), [
            Property(anchor.create_renamed('list'), is_association=True, associated_value=[
                associated_value_to_expression(anchor, i) for i in value
            ])
        ])
    elif isinstance(value, bytes):  # TODO we're just assuming bytes are always strings which is dangerous
        return associated_value_to_expression(anchor, value.decode(), name)
    elif isinstance(value, Expression):
        return value
    else:
        perror(ErrorMessage.BAD_TYPE, value, 'Expression', anchor=anchor)

def get_defn_file(source_type_object) -> str:
    return inspect.getfile(source_type_object) or "<imported file>"
def get_defn_line(source_type_object) -> int:
    try:            return inspect.getsourcelines(source_type_object)[1]
    except OSError: return 0


# Helper functions for apply callables
def pick_self(self, expr, args, scope, prop) -> Any:
    return self
def pick_lhs(self, expr, args, scope, prop) -> Expression:
    return expr
def pick_rhs(self, expr, args: list[Expression], scope, prop) -> Expression:
    if len(args) ==  1: return args[0]
    perror(f"{prop}: expected exactly one argument for rhs, got {args}", anchor=prop)
def pick_args(self, expr, args: list[Expression], scope, prop) -> list[Expression]:
    return args
def pick_scope(self, expr, args, scope, prop) -> Scope:
    return scope
def pick_prop(self, expr, args, scope, prop) -> Property:
    return prop

def define_apply(func: Callable):
    '''We do inheritance checking in the apply method of the classes, not here'''
    extractors = {
        'self': pick_self,
        'lhs': pick_lhs, 'rhs': pick_rhs,
        'args':pick_args,'body':pick_args,
        'scope':pick_scope,
        'prop':pick_prop
    }
    # Precompute once
    sig = inspect.signature(func)
    param_extractors = [
        extractors[name]
        for name in sig.parameters
    ]
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope, prop: Property) -> Expression:
        values = [
            extractor(self, lhs, args, scope, prop)
            for extractor in param_extractors
        ]
        return associated_value_to_expression(lhs.symbol, func(*values))
    return apply

# Decorator
def register_definition(symbol: str, property_names: list[PropertyLiteral] = [], param_names: list[ExpressionLiteral] = [], is_compound: bool = False):
    def decorator[T](func: T) -> T:
        assert callable(func)
        file, row = get_defn_file(func), get_defn_line(func)
        anchor = Provenance(file, row, 0)
        props = literal_pack_to_property(property_names, anchor)
        params = literal_pack_to_expression(param_names, anchor)
        defn = _LambdaDefinition(symbol, props, is_compound, params, [], define_apply(func))
        
        global_definitions.setdefault(symbol, []).append(defn)
        return func
    return decorator

class _LambdaDefinition(Definition):
    def __init__(self, prop_symb: str, properties: list[Property], is_compound: bool, params: list[Expression], 
                 body: list[Expression], apply_callable: Callable, scope: 'Scope|None' = None):
        # Find the location where we are defining this function
        inspect_stack = inspect.stack()
        assert len(inspect_stack) > 2
        parent = inspect_stack[2]
        super().__init__(prop_symb, properties, is_compound, params, body, scope, parent.filename, parent.lineno)
        self.apply_callable = apply_callable
    def apply(self, expr: Expression, args: list[Expression], scope: 'Scope', prop: Property) -> Expression:
        if len(self.params) > len(args):
            perror(ErrorMessage.BAD_NUMBER_ARGS, self.params, self, args, anchor=expr)
        for param, arg in zip(self.params, args):
            if not inherits(arg, param):
                perror(ErrorMessage.BAD_TYPE, arg, param, anchor=expr)
        self.trace_stack.append((expr, args, scope, prop))
        res = self.apply_callable(self, expr, args, scope, prop)
        self.trace_stack.pop()
        return res
    
# --------------------------------------------------
# Definitions begin below
# --------------------------------------------------

@register_definition('assign', ['identifier'], ['rval'])
def assign(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    if (expr := scope.var_lookup(lhs.symbol.s)) is None:
        expr = lhs.copy().discard_property('identifier')
        scope.local_vars[lhs.symbol.s] = expr
    
    for p in rhs.properties:
        if (val := expr.try_get_property(p.property.s)) is None:
            expr.properties.append(p.copy())
        else:
            val.is_association = p.is_association
            val.associated_value = p.associated_value
            val.is_compound = p.is_compound
            val.compound_properties = p.compound_properties
    return rhs
    
@register_definition('assert', ['integer'])
def assert_(lhs: Expression) -> Expression:
    ival = lhs.force_get_property('integer')
    if ival.associated_value == 0:
        perror(f"assertion failed {lhs}", anchor=lhs)
    return lhs
    
# Control flow

@register_definition('else', ['integer'], ['false_branch...'])
def else_(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    ival = lhs.force_get_property('integer')
    if ival.associated_value == 0:
        from main import expression_resolve_all
        for expr in body:
            res = expression_resolve_all(expr, scope, constants.resolve)
        return res
    return lhs

@register_definition('then', ['integer'], ['true_branch...'])
def then(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    ival = lhs.force_get_property('integer')
    if ival.associated_value != 0:
        from main import expression_resolve_all
        for expr in body:
            res = expression_resolve_all(expr, scope, constants.resolve)
        return res
    return lhs

@register_definition('else', ['integer', 'then'], ['false_branch...'])
def then_else(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    ival = lhs.force_get_property('integer')
    then_prop = lhs.force_get_property('then')
    lhs, _ = lhs.discard_properties_after('then')
    from main import expression_resolve_all
    if ival.associated_value == 0:
        for expr in body:
            res = expression_resolve_all(expr, scope, constants.resolve)
        return res
    else:
        for expr in then_prop.compound_properties:
            res = expression_resolve_all(expr, scope, constants.resolve)
        return res

# Misc.

@register_definition('declare', ['identifier'])
def declare(lhs: Expression, scope: Scope) -> Expression:
    scope.local_vars[lhs.symbol.s] = Expression(lhs.symbol, [
        p.copy() for p in lhs.properties if p.property != 'identifier'
    ])
    return lhs


def get_context(scope: Scope, existing: list[Property]|None = None) -> list[Property]:
    if existing is None:
        existing = []
    context_expr = scope.local_vars.get('__CONTEXT__')
    if context_expr is not None:
        existing.extend(context_expr.properties)
    if scope.parent is not None:
        get_context(scope.parent, existing)
    return existing

@register_definition('context')
def update_context(lhs: Expression, scope: Scope) -> Expression:
    # contexts define properties to be inherited, which are given by lhs
    existing_context = scope.local_vars.get('__CONTEXT__', Expression(lhs.symbol.create_renamed('__CONTEXT__'), []))
    existing_context.properties += [p.copy() for p in lhs.properties]
    scope.local_vars['__CONTEXT__'] = existing_context
    return lhs

def expand_typed_properties(expr: Expression) -> Expression:
    # Expands the "is" property into properties
    if (is_prop := expr.try_get_property('is')) is None:
        return expr
    props = [Property(expr.symbol) for expr in is_prop.compound_properties]
    expr = expr.discard_property('is')
    expr.properties += props
    return expr
    
@register_definition('definition', [], ['body...'])
def definition(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    lhs = lhs.discard_property('identifier')
    p = lhs.properties.pop()
    lhs = expand_typed_properties(lhs)
    p.compound_properties = [
        expand_typed_properties(e.discard_property('identifier')) for e in p.compound_properties
    ]

    # add to definitions
    from main import UserDefinedDefinition
    ret =  UserDefinedDefinition(lhs.symbol.s, lhs.properties, 
                   p.is_compound, p.compound_properties, body, scope, p.property.file, p.property.row)
    scope.local_defns.setdefault(p.property.s, []).append(ret)
    return Expression(p.property, [
        Property(p.property.create_renamed('property'), is_association=True, associated_value=(p, ret))
    ])

@register_definition('return', ['definition'], ['body...'])
def return_(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    # TODO do we even do anything about types here?
    # body is the type we want for our lhs, but we can only know the type during function call
    from main import resolve_property_on
    lhs, defn_prop = lhs.discard_properties_after('definition')
    return resolve_property_on(lhs, defn_prop, scope, [])
    
@register_definition('do', [], ['body...'])
def do(lhs: Expression) -> Expression:
    return lhs

@register_definition('identifier')
def identifier(lhs: Expression, scope: Scope) -> Expression:
    if (val := scope.var_lookup(lhs.symbol.s)) is None:
        return pwarning(ErrorMessage.NO_IDENTIFIER, lhs, anchor=lhs)
    ret = val.copy()
    ret.symbol = lhs.symbol # update the token (file, line, etc) for error messages
    return ret
    
# List operators

def create_list(anchor: Token, value: list[Expression]) -> Expression:
    res_properties = [Property(anchor.create_renamed('list'))]
    res_properties[0].is_association = True
    res_properties[0].associated_value = value
    res = Expression(anchor, res_properties)
    return res

# Logical operators

@register_definition('logical_not', ['integer'])
def logical_not(lhs: Expression) -> Expression:
    ival = lhs.force_get_property('integer')
    updated_ival = ival.copy()
    updated_ival.is_association = True
    updated_ival.associated_value = not updated_ival.associated_value
    return lhs.replace_property('integer', updated_ival)

# Property operators

@register_definition('inherits', [], ['super'])
# TODO stop calling inherits directly and replace with main.resolve_property_on
def inherits(lhs: Expression, rhs: Expression) -> bool:
    # TODO here we assume that lhs properties can be treated as unique
    ''' 
    lhs is said to inherit rhs if
    lhs's properties is a superset of rhs's properties
    '''
    lhs_props = {prop.property.s:prop for prop in lhs.properties}
    for rhs_prop in rhs.properties:
        if rhs_prop.property.s not in lhs_props:
            return False
        lhs_prop = lhs_props[rhs_prop.property.s]
        if len(rhs_prop.compound_properties) > len(lhs_prop.compound_properties):
            return False
        for lexpr, rexpr in zip(lhs_prop.compound_properties, rhs_prop.compound_properties):
            if not inherits(lexpr, rexpr):
                return False
    return True

@register_definition('properties')
def properties(lhs: Expression) -> list[Expression]:
    res_list: list[Expression] = []
    for p in lhs.properties:
        res_list.append(Expression(p.property, [
            Property(p.property.create_renamed('property'), is_association=True, associated_value=p)
        ]))
    return res_list

@register_definition('\\', [], ['properties_to_remove...'])
def remove_property(lhs: Expression, args: list[Expression]) -> Expression:
    properties_to_remove = set(arg.symbol.s for arg in args)
    new_properties = [p for p in lhs.properties if p.property.s not in properties_to_remove]
    return Expression(lhs.symbol, new_properties)

# Types - these are idempotent

@register_definition('integer')
@register_definition('string')
def idempotent(lhs: Expression, prop: Property) -> Expression:
    return lhs.create_with_property(prop)