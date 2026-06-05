import inspect
import sys
import os
from typing import Any, Callable
from errors import perror, pwarning, ErrorMessage

from constants import Definition, ProvenanceAware, Scope, Expression, Property, Token, token_types
import constants

__LANG__ = '0.0.2'
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
    else:
        perror(f'unable to convert associated value {value} of type {type(value)} to expression in {name}', anchor=anchor)

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
        return func(*values)
    return apply

# Decorator
def register_definition(symbol: str, property_names: list[str] = [], param_names: list[str] = [], is_compound: bool = False):
    def decorator[T](func: T) -> T:
        assert callable(func)
        file = get_defn_file(func)
        row = get_defn_line(func)
        props = [Property(Token(p_name, file, row, 0, token_types['alnum'])) for p_name in property_names]
        params = [Expression(Token(param_name, file, row, 0, token_types['alnum']), []) for param_name in param_names]
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
        self.trace_stack.append((expr, args, scope, prop))
        res = self.apply_callable(self, expr, args, scope, prop)
        self.trace_stack.pop()
        return res


# Definitions begin below

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
    
@register_definition('definition', [], ['body...'])
def definition(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    lhs = lhs.discard_property('identifier')
    p = lhs.properties.pop()
    p.compound_properties = [e.discard_property('identifier') for e in p.compound_properties]

    # add to definitions
    from main import UserDefinedDefinition
    scope.local_defns.setdefault(p.property.s, []).append(
        UserDefinedDefinition(lhs.symbol.s, lhs.properties, 
                   p.is_compound, p.compound_properties, body, scope, p.property.file, p.property.row)
    )
    return Expression(p.property, [
        Property(p.property.create_renamed('property'), is_association=True, associated_value=p)
    ])
    
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

# Imports

def _find_import_file(anchor: ProvenanceAware, path: str):
    path_relative = os.path.join(os.path.dirname(anchor.get_source().file), path)
    path_library = path
    if os.path.exists(path_relative):
        return path_relative
    elif os.path.exists(path_library):
        return path_library
    else:
        perror(f'unable to resolve path {path}', anchor=anchor)

@register_definition('run', ['string'])
def run(lhs: Expression, scope: Scope) -> Expression:
    path = lhs.force_get_property('string')
    path_str = _find_import_file(lhs, path.associated_value)
    from main import run_file
    run_file(path_str)
    return lhs

imported_files: dict[str, Scope] = {} # maps paths to global variable dicts, to avoid duplicate imports
@register_definition('import', ['string'], ['import_signatures...'])
def import_(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    path = lhs.force_get_property('string')
    path_str = _find_import_file(lhs, path.associated_value)
    if path_str in imported_files:
        imported_globals = imported_files[path_str]
    else:
        from main import run_file
        imported_globals = run_file(path_str)
        imported_files[path_str] = imported_globals
    for imported_symbol in body:
        symb = imported_symbol.symbol.s
        if symb in imported_globals.local_vars:
            scope.local_vars[symb] = imported_globals.local_vars[symb]
        elif symb in imported_globals.local_defns:
            scope.local_defns.setdefault(symb, []).extend(imported_globals.local_defns[symb])
        else:
            pwarning(ErrorMessage.NO_IMPORT_SYMBOL, symb, path_str, anchor=imported_symbol)
    return lhs

class ImportedSharedDefinition(Definition):
    def __init__(self, name: str, is_compound: bool, func: Callable, source_file: str):
        # TODO somehow check the number of arguments of the function
        super().__init__(name, [], is_compound, [], [])
        self.func = func
    @define_apply
    def apply(self, lhs: Expression, args: list[Expression]) -> Expression:
        self_value = expression_to_associated_value(lhs)
        arg_values = [expression_to_associated_value(arg) for arg in args]
        res = self.func(self_value, *arg_values)
        return associated_value_to_expression(lhs.symbol, res)

@register_definition('import', ['string', 'shared'], ['import_signatures...'])
def import_shared(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    path = lhs.try_get_property('string')
    assert path is not None
    # Import the shared library file
    path_str = os.path.abspath(_find_import_file(lhs, path.associated_value))
    import ctypes
    lib = ctypes.CDLL(path_str)
    ## TODO signature definition
    for definition in body:
        symbol_name = definition.symbol.s
        defn_list = scope.local_defns.setdefault(symbol_name, [])
        defn_list.append(ImportedSharedDefinition(symbol_name, True, lib[symbol_name], path_str))
        defn_list.append(ImportedSharedDefinition(symbol_name, False, lib[symbol_name], path_str))
    return lhs

class ImportedPythonDefinition(Definition):
    def __init__(self, func: Callable, source_file: str):
        symbol = func.__name__
        # Get the parameters
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())
        _, *param_names = param_names
        def token(s: str):
            return Token(s, source_file, 0, 0, token_types['alnum']) # TODO better row accuracy
        super().__init__(symbol, [], 
                         len(param_names) > 0, [Expression(token(s), []) for s in param_names], [])
        self.func = func
    @define_apply
    def apply(self, lhs: Expression, args: list[Expression]) -> Expression:
        self_value = expression_to_associated_value(lhs)
        arg_values = [expression_to_associated_value(arg) for arg in args]
        res = self.func(self_value, *arg_values)
        return associated_value_to_expression(lhs.symbol, res)

def import_raw_python_file(anchor: Expression, path: str, imports: list[str], scope: Scope):
    path_str = _find_import_file(anchor, path)
    captured_globals: dict = make_global_vars(path_str)
    captured_globals['__file__'] = path_str
    with open(path_str, 'r') as f:
        content = f.read()
    # TODO make this safe
    code = compile(content, path_str, 'exec')
    exec(code, captured_globals)
    res = {}
    for symbol in imports:
        if symbol not in captured_globals:
            pwarning(ErrorMessage.NO_IMPORT_SYMBOL, symbol, path_str, anchor=anchor)
            continue
        defn_impl = captured_globals[symbol]
        if callable(defn_impl):
            scope.local_defns.setdefault(symbol, []).append(ImportedPythonDefinition(defn_impl, path_str))
        else:
            start_line = get_defn_line(defn_impl)
            scope.local_vars[symbol] = associated_value_to_expression(
                Token(symbol, path_str, start_line, 0, token_types['alnum']), defn_impl, symbol)
    return res
        

@register_definition('import', ['string', 'python'], ['import_signatures...'])
def import_python(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    path = lhs.force_get_property('string')
    # Load in the python file
    import_raw_python_file(lhs, path.associated_value, [defn.symbol.s for defn in body], scope)
    return lhs

past_imports = {}
def import_module(anchor: ProvenanceAware, path_str: str):
    import importlib.util
    path_str = _find_import_file(anchor, path_str)
    # Get string from path_str
    module_name = os.path.splitext(os.path.basename(path_str))[0]

    spec = importlib.util.spec_from_file_location(module_name, path_str)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    # Check if we have already imported this module to avoid duplicates
    if module_name in past_imports: return past_imports[module_name]
    else: past_imports[module_name] = module

    sys.modules[module_name] = module
    # for convenience, we also allow access to the global definitions dict
    setattr(module, 'global_definitions', global_definitions)
    # and some of the modules
    setattr(module, 'constants', constants)
    setattr(module, 'definitions', sys.modules[__name__])
    spec.loader.exec_module(module)
    return module

@register_definition('import', ['string', 'python', 'definition'], ['import_signatures...'])
def import_python_definition(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    path = lhs.force_get_property('string')
    # Load in the python file
    import_module(lhs, path.associated_value)
    return lhs
    
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

@register_definition('properties')
def properties(lhs: Expression) -> Expression:
    res_list = []
    for p in lhs.properties:
        res_list.append(Expression(p.property, [
            Property(p.property.create_renamed('property'), is_association=True, associated_value=p)
        ]))
    return create_list(lhs.symbol, res_list)

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