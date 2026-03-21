import inspect
import sys
import os
from typing import Any, Callable, NoReturn
from functools import wraps

from constants import Definition, Scope, Expression, Property, Token

__LANG__ = '0.0.1'
global_definitions: dict[str, list[Definition]] = {}

class CompileError(Exception):
    def __init__(self, *msg, anchor: Token|None = None):
        header = "Error:" if anchor is None else f"Error at {anchor.file}:{anchor.row}:{anchor.col}:"
        super().__init__(header, *msg)

def pwarning(*msg, anchor:Token|None=None):
    header = "Warning:" if anchor is None else f"Warning at {anchor.file}:{anchor.row}:{anchor.col}:"
    print(header, *msg, file=sys.stderr)

def remove_property(properties: list['Property'], property_name: str, reverse: bool=False) -> bool:
    seq = reversed(range(len(properties))) if reverse else range(len(properties))
    for i in seq:
        if properties[i].property == property_name:
            properties.pop(i)
            return True
    return False

def expression_to_associated_value(expr: Expression) -> Any:
    if (ival := expr.try_get_property('integer')) is not None:
        return ival.associated_value
    elif (sval := expr.try_get_property('string')) is not None:
        return sval.associated_value
    elif (lval := expr.try_get_property('list')) is not None:
        return [expression_to_associated_value(e) for e in lval.associated_value]
    else:
        raise CompileError(f'unable to convert {expr} to associated value')

def associated_value_to_expression(anchor: Token, value: Any, name=None) -> Expression:
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
        raise CompileError(f'unable to convert associated value {value} of type {type(value)} to expression in {name}')

def get_defn_file(defn_class) -> str:
    return inspect.getfile(defn_class) or "<imported file>"
def get_defn_line(defn_class) -> int:
    try:            return inspect.getsourcelines(defn_class)[1]
    except OSError: return 0

def build_defn_instance(defn_class) -> Definition:
    symbol: str = defn_class.symbol
    file = get_defn_file(defn_class)
    row = get_defn_line(defn_class)
    if hasattr(defn_class, 'param_names'):
        is_compound = True
        params = [Expression(Token(param_name, file, row, 0), []) 
                  for param_name in defn_class.param_names]
    else:
        is_compound = False
        params = []

    if hasattr(defn_class, 'property_names'):
        properties: list[Property] = [Property(Token(p_name, file, row, 0)) 
                                      for p_name in defn_class.property_names]
    else:
        properties = []
    return defn_class(symbol, properties, is_compound, params, [])

def builtin_definition(defn_class):
    global_definitions.setdefault(defn_class.symbol, []).append(
        build_defn_instance(defn_class)
    )

def binary_apply(func: Callable[[Any, Expression, Expression, Scope], Expression]):
    '''
    unwarps the apply args to a single argument
    '''
    @wraps(func)
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        return func(self, lhs, args[0], scope)
    return apply

# Definitions begin below

@builtin_definition
class AssignDefinition(Definition):
    symbol = 'assign'
    param_names = ['rval']
    property_names = ['identifier']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (expr := scope.var_lookup(lhs.symbol.s)) is None:
            expr = Expression(lhs.symbol, [
                p.copy() for p in lhs.properties if p.property.s != 'identifier'
            ])
            scope.local_vars[lhs.symbol.s] = expr
        
        for p in rhs.properties:
            if (val := expr.try_get_property(p.property.s)) is None:
                expr.properties.append(p.copy())
            else:
                if p.is_association:
                    val.is_association = True
                    val.associated_value = p.associated_value
                if p.is_compound:
                    val.is_compound = True
                    val.compound_properties = p.compound_properties
        return rhs
    
@builtin_definition
class AssertDefinition(Definition):
    symbol = 'assert'
    param_names = ['assertion']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (ival := rhs.try_get_property('integer')) is None:
            pwarning(f"assertion can not be applied to {rhs}")
        elif ival.associated_value == 0:
            raise CompileError(f"assertion failed {rhs}")
        return lhs
    
# Control flow

@builtin_definition
class ControlElseDefinition(Definition):
    symbol = 'else'
    param_names = ['false_branch']
    property_names = ['integer']
    def apply(self, lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
        ival = lhs.try_get_property('integer')
        assert ival is not None
        if ival.associated_value == 0:
            from main import resolve_last_property
            res = lhs
            for expr in body:
                res = resolve_last_property(expr, scope)
            return res
        else:
            # pop all properties until 'then' or empty
            properties = lhs.properties.copy()
            while len(properties) > 0 and properties[-1].property.s != 'then':
                properties.pop()
            if len(properties) == 0:
                return lhs
            from main import resolve_last_property
            return resolve_last_property(Expression(lhs.symbol, properties), scope)

@builtin_definition
class ControlThenDefinition(Definition):
    symbol = 'then'
    param_names = ['true_branch']
    property_names = ['integer']
    def apply(self, lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
        ival = lhs.try_get_property('integer')
        assert ival is not None
        if ival.associated_value != 0:
            from main import resolve_last_property
            res = lhs
            for expr in body:
                res = resolve_last_property(expr, scope)
            return res
        else:
            return lhs

# Misc.

@builtin_definition
class DeclareDefinition(Definition):
    symbol = 'declare'
    property_names = ['identifier']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        scope.local_vars[lhs.symbol.s] = Expression(lhs.symbol, [
            p.copy() for p in lhs.properties if p.property != 'identifier'
        ])
        return lhs
    
@builtin_definition
class DefinitionDefinition(Definition):
    symbol = 'definition'
    param_names = ['body']
    def apply(self, lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
        *placeholder_properties, p = lhs.properties
        # remove 'identifier' from properties and parameters
        remove_property(placeholder_properties, 'identifier')
        parameters = [Expression(e.symbol, e.properties) for e in p.compound_properties]
        for e in parameters:
            remove_property(e.properties, 'identifier')

        # add to definitions
        from main import UserDefinedDefinition
        scope.local_defns.setdefault(p.property.s, []).append(
            UserDefinedDefinition(lhs.symbol.s, placeholder_properties, 
                       p.is_compound, p.compound_properties, body)
        )
        return Expression(p.property, [
            Property(p.property.create_renamed('property'), is_association=True, associated_value=p)
        ])
    
@builtin_definition
class DoDefinition(Definition):
    symbol = 'do'
    param_names = ['body']
    def apply(self, lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
        return lhs
    
@builtin_definition
class FieldGetDefinition(Definition):
    symbol = 'field_get'
    param_names = ['field_name_symbol']
    property_names = ['structure']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        val = lhs.try_get_property('structure')
        assert val is not None
        field = rhs.symbol
        if field not in val.associated_value:
            raise CompileError(f"{lhs} has no field {rhs}")
        return val.associated_value[field]

@builtin_definition
class FieldSetDefinition(Definition):
    symbol = 'field_set'
    param_names = ['field']
    property_names = ['structure']
    def apply(self, lhs: Expression, rhs: list[Expression], scope: Scope) -> Expression:
        val = lhs.try_get_property('structure')
        assert val is not None
        # Just in case it is None-value
        if not val.is_association:
            val.is_association = True
            val.associated_value = {}
        for expr in rhs:
            val.associated_value[expr.symbol] = expr
        return lhs

@builtin_definition
class IdentifierDefinition(Definition):
    symbol = 'identifier'
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        if (val := scope.var_lookup(lhs.symbol.s)) is None:
            raise CompileError(f"unable to resolve identifier {lhs}")
        return val
    
def find_import_file(path_anchor: str, path: str):
    path_relative = os.path.join(os.path.dirname(path_anchor), path)
    path_library = path
    if os.path.exists(path_relative):
        return path_relative
    elif os.path.exists(path_library):
        return path_library
    else:
        raise CompileError(f'unable to resolve path {path}')

class ImportedPythonDefinition(Definition):
    def __init__(self, func: Callable, source_file: str):
        symbol = func.__name__
        # Get the parameters
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())
        placeholder_symb, *param_names = param_names
        def token(s: str):
            return Token(s, source_file, 0, 0) # TODO better row accuracy
        super().__init__(placeholder_symb, [], 
                         len(param_names) > 0, [Expression(token(s), []) for s in param_names], [])
        self.func = func
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        self_value = expression_to_associated_value(lhs)
        arg_values = [expression_to_associated_value(arg) for arg in args]
        res = self.func(self_value, *arg_values)
        return associated_value_to_expression(lhs.symbol, res)

def import_raw_python_file(path_anchor: str, path: str, imports: list[str], scope: Scope):
    path_str = find_import_file(path_anchor, path)
    empty_globals = {}
    with open(path_str, 'r') as f:
        content = f.read()
    # TODO make this safe
    code = compile(content, path_str, 'exec')
    exec(code, empty_globals)
    res = {}
    for symbol in imports:
        if symbol not in empty_globals:
            pwarning(f"unable to import {symbol} from {path_str}")
            continue
        defn_impl = empty_globals[symbol]
        if callable(defn_impl):
            scope.local_defns.setdefault(symbol, []).append(ImportedPythonDefinition(defn_impl, path_str))
        else:
            start_line = get_defn_line(defn_impl)
            scope.local_vars[symbol] = associated_value_to_expression(
                Token(symbol, path_str, start_line, 0), defn_impl, symbol)
    return res
        

@builtin_definition
class ImportRawPythonDefinition(Definition):
    symbol = 'import'
    property_names = ['string', 'python']
    param_names = ['definitions...']
    # We need to name which Python variables/functions to import.
    # Functions are imported as `foo(bar, baz) == bar foo(baz)` and no type safety
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        path = lhs.try_get_property('string')
        assert path is not None
        # Load in the python file by executing it in an empty global scope,
        # then we will copy over the specified variables/functions into `scope`.
        imports = [defn.symbol.s for defn in args]
        import_raw_python_file(lhs.symbol.file, path.associated_value, imports, scope)
        return lhs

@builtin_definition
class ImportPythonDefinition(Definition):
    symbol = 'import'
    property_names = ['string', 'python', 'definition']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        path = lhs.try_get_property('string')
        assert path is not None
        # Load in the python file
        path_str = find_import_file(lhs.symbol.file, path.associated_value)
        ## TODO make this safe
        with open(path_str, 'r') as f:
            content = f.read()
        code = compile(content, path_str, 'exec')
        exec(code, globals())
        return lhs
    
# List operators

def create_list(anchor: Token, value: list[Expression]) -> Expression:
    res_properties = [Property(anchor.create_renamed('list'))]
    res_properties[0].is_association = True
    res_properties[0].associated_value = value
    res = Expression(anchor, res_properties)
    return res

@builtin_definition
class ListAppendDefinition(Definition):
    symbol = 'append'
    property_names = ['list']
    param_names = ['item']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        dst = lhs.try_get_property('list')
        assert dst is not None
        dst.is_association = True
        dst.associated_value = dst.associated_value or []
        dst.associated_value.append(rhs)
        return rhs
    
@builtin_definition
class ListEachDefinition(Definition):
    symbol = 'each'
    property_names = ['list']
    param_names = ['callback_property']
    @binary_apply
    def apply(self, lhs: Expression, callback: Expression, scope: Scope) -> Expression:
        iterable = lhs.try_get_property('list')
        assert iterable is not None 
        if iterable.associated_value is None:
            return lhs
        if (pval := callback.try_get_property('property')) is None:
            raise CompileError(f'`each` requires a property argument, got {callback}')
        prop = pval.associated_value
        assert prop is not None
        from main import resolve_expression, resolve_last_property
        res: list[Expression] = []
        for item in iterable.associated_value:
            # item is an Expression
            expr = Expression(item.symbol, 
                              item.properties + [prop])
            res.append(resolve_last_property(expr, scope))
        return create_list(lhs.symbol, res)

@builtin_definition
class ListIndexDefinition(Definition):
    symbol = 'index'
    property_names = ['list']
    param_names = ['index']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        dst = lhs.try_get_property('list')
        assert dst is not None
        if (isrc := rhs.try_get_property('integer')) is None:
            raise CompileError(f'unable to index {lhs} with {rhs}')
        if not isinstance(dst.associated_value, list) or \
                isrc.associated_value >= len(dst.associated_value):
            raise CompileError(f'index out of bounds on {lhs} with {rhs}')
        return dst.associated_value[isrc.associated_value]

# Logical operators

@builtin_definition
class LogicalNotDefinition(Definition):
    symbol = 'logical_not'
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        if (ival := lhs.try_get_property('integer')) is None:
            pwarning(f"logical not can not be applied to {lhs}")
            return lhs
        else:
            updated_ival = ival.copy()
            updated_ival.is_association = True
            updated_ival.associated_value = not updated_ival.associated_value
            properties = [updated_ival if property == ival else property for property in lhs.properties]
            return Expression(lhs.symbol, properties)
    
@builtin_definition
class PropertiesDefinition(Definition):
    symbol = 'properties'
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        res_list = []
        for p in lhs.properties:
            res_list.append(Expression(p.property, [
                Property(p.property.create_renamed('property'), is_association=True, associated_value=p)
            ]))
        return create_list(lhs.symbol, res_list)
