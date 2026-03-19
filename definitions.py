import inspect
import sys
import os
from typing import Any, Callable, NoReturn
from functools import wraps

from constants import Definition, Scope, Expression, Property, Token

__LANG__ = '0.0.1'
global_definitions: dict[str, list[Definition]] = {}

class CompileError(Exception):
    pass

def perror(*msg) -> NoReturn:
    print("Error:", *msg, file=sys.stderr)
    raise CompileError()

def pwarning(*msg):
    print("Warning:", *msg, file=sys.stderr)

def remove_property(properties: list['Property'], property_name: str, reverse: bool=False) -> bool:
    seq = reversed(range(len(properties))) if reverse else range(len(properties))
    for i in seq:
        if properties[i].property == property_name:
            properties.pop(i)
            return True
    return False


def build_defn_instance(defn_class) -> Definition:
    symbol: str = defn_class.symbol
    file = inspect.getfile(defn_class)
    _, row = inspect.getsourcelines(defn_class)
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
    return defn_class(symbol, properties, is_compound, params, 
                   Expression(Token('body', file, row, 0), []))

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
            perror(f"assertion failed {rhs}")
        return lhs
    
@builtin_definition
class ArithmeticAddDefinition(Definition):
    symbol = '+'
    param_names = ['operand']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (ival := rhs.try_get_property('integer')) is None or \
            (idst := lhs.try_get_property('integer')) is None:
            perror(f"unable to add {rhs} to {lhs}")
        ires = idst.copy()
        ires.is_association = True
        ires.associated_value += ival.associated_value
        res_properties = [
            ires if property == idst else property for property in lhs.properties
        ]
        return Expression(lhs.symbol.create_renamed('+'), res_properties)

@builtin_definition
class ArithmeticEqualDefinition(Definition):
    symbol = '=='
    param_names = ['operand']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.try_get_property('integer')
        rval = rhs.try_get_property('integer')
        assert lval is not None and rval is not None
        res = lval.associated_value == rval.associated_value
        return Expression(lhs.symbol.create_renamed('=='), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
        ])    

@builtin_definition
class ArithmeticLessThanDefinition(Definition):
    symbol = '<'
    param_names = ['operand']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (ival := rhs.try_get_property('integer')) is None or \
            (idst := lhs.try_get_property('integer')) is None:
            perror(f"unable to check {rhs} < {lhs}")
        res = idst.associated_value < ival.associated_value
        return Expression(lhs.symbol.create_renamed('<'), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
        ])

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
            perror(f"{lhs} has no field {rhs}")
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
            perror(f"unable to resolve identifier {lhs}")
        return val
    
@builtin_definition
class ImportPythonDefinition(Definition):
    symbol = 'import'
    property_names = ['string', 'python']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        path = lhs.try_get_property('string')
        assert path is not None
        # Load in the python file
        path_relative = os.path.join(os.path.dirname(lhs.symbol.file), path.associated_value)
        path_library = path.associated_value
        if os.path.exists(path_relative):
            path_str = path_relative
        elif os.path.exists(path_library):
            path_str = path_library
        else:
            perror(f'unable to resolve path {path.associated_value}')
        
        ## TODO make this safe
        with open(path_str, 'r') as f:
            content = f.read()
        exec(content, globals=globals())
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
    param_names = ['prev_placeholder', 'body']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        iterable = lhs.try_get_property('list')
        assert iterable is not None 
        if iterable.associated_value is None:
            return lhs
        item_placeholder, body = args
        from main import resolve_expression, resolve_last_property
        res: list[Expression] = []
        for item in iterable.associated_value:
            # item is an Expression
            local_scope = Scope({item_placeholder.symbol.s: item}, parent_scope=scope)
            local_body = resolve_expression(body, local_scope)
            res.append(resolve_last_property(local_body, local_scope))
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
            perror(f'unable to index {lhs} with {rhs}')
        if not isinstance(dst.associated_value, list) or \
                isrc.associated_value >= len(dst.associated_value):
            perror(f'index out of bounds on {lhs} with {rhs}')
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

@builtin_definition
class ResolutionDefinition(Definition):
    symbol = 'resolution'
    param_names = ['body']
    @binary_apply
    def apply(self, lhs: Expression, body: Expression, scope: Scope) -> Expression:
        *placeholder_properties, property = lhs.properties
        # remove 'identifier' from properties and parameters
        remove_property(placeholder_properties, 'identifier')
        parameters = [Expression(e.symbol, e.properties) for e in property.compound_properties]
        for e in parameters:
            remove_property(e.properties, 'identifier')

        # add to definitions
        from main import UserDefinedDefinition
        scope.local_defns.setdefault(property.property.s, []).append(
            UserDefinedDefinition(lhs.symbol.s, placeholder_properties, 
                       property.is_compound, property.compound_properties, body)
        )
        return lhs