import inspect
import sys
import os
import ast
from typing import NoReturn
from functools import wraps

from constants import Definition, Scope, Expression, Property, Token, expand_property

__LANG__ = '0.0.1'
global_definitions: dict[str, list[Definition]] = {}

def perror(*msg) -> NoReturn:
    print("Error:", *msg, file=sys.stderr)
    sys.exit(1)

def pwarning(*msg):
    print("Warning:", *msg, file=sys.stderr)


def builtin_defn(defn_class):
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

    global_definitions.setdefault(symbol, []).append(
        defn_class(symbol, properties, is_compound, params, 
                   Expression(Token('body', file, row, 0), []))
    )

def binary_apply(func):
    '''
    unwarps the apply args to a single argument
    '''
    @wraps(func)
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        return func(self, lhs, args[0], scope)
    return apply

# Utility to find all classes decorated with @builtin_defn
class DecoratedDefinitionVisitor(ast.NodeVisitor):
    def __init__(self, decorator_name):
        self.decorator_name = decorator_name
        self.decorated_defs: list[ast.ClassDef] = []

    def visit_ClassDef(self, node):
        self._check_decorators(node)
        # Ensure we visit nested functions/classes
        self.generic_visit(node)

    def _check_decorators(self, node: ast.ClassDef):
        for decorator in node.decorator_list:
            # Check for simple decorators like @my_decorator
            if isinstance(decorator, ast.Name) and decorator.id == self.decorator_name:
                self.decorated_defs.append(node)
                break
            # Check for decorators with arguments like @my_decorator(arg=1)
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name) and decorator.func.id == self.decorator_name:
                    self.decorated_defs.append(node)
                    break


# Definitions begin below

@builtin_defn
class AssignDefinition(Definition):
    symbol = 'assign'
    param_names = ['rval']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if lhs.try_get_property('identifier') is None:
            pwarning(f"assigning to non-identifier {lhs}")
            return rhs
        
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
    
@builtin_defn
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
    
@builtin_defn
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

@builtin_defn
class ArithmeticEqualDefinition(Definition):
    symbol = '=='
    param_names = ['operand']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        if (ival := rhs.try_get_property('integer')) is None or \
            (idst := lhs.try_get_property('integer')) is None:
            perror(f"unable to check {rhs} == {lhs}")
        res = idst.associated_value == ival.associated_value
        return Expression(lhs.symbol.create_renamed('=='), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
        ])    

@builtin_defn
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


# Misc.

@builtin_defn
class DeclareDefinition(Definition):
    symbol = 'declare'
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        if lhs.try_get_property('identifier') is None:
            pwarning(f"declaring non-identifier {lhs}")
        scope.local_vars[lhs.symbol.s] = Expression(lhs.symbol, [
            p.copy() for p in lhs.properties if p.property != 'identifier'
        ])
        return lhs
    
@builtin_defn
class DoDefinition(Definition):
    symbol = 'do'
    param_names = ['body']
    def apply(self, lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
        return lhs
    
@builtin_defn
class IdentifierDefinition(Definition):
    symbol = 'identifier'
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        if (val := scope.var_lookup(lhs.symbol.s)) is None:
            perror(f"unable to resolve identifier {lhs}")
        return val
    
@builtin_defn
class ImportPythonDefinition(Definition):
    symbol = 'import'
    property_names = ['string', 'python']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        path = lhs.try_get_property('string')
        assert path is not None
        # Load in the python file
        print(lhs.symbol.file, path.associated_value)
        path_relative = os.path.join(os.path.dirname(lhs.symbol.file), path.associated_value)
        path_library = path.associated_value
        if os.path.exists(path_relative):
            path_str = path_relative
        elif os.path.exists(path_library):
            path_str = path_library
        else:
            perror(f'unable to resolve path {path.associated_value}')
        
        ## TODO make this safe
        # with open(path_str, 'r') as f:
        #     tree = ast.parse(f.read(), filename=path_str)
        # visitor = DecoratedDefinitionVisitor('class_defn')
        # visitor.visit(tree)
        with open(path_str, 'r') as f:
            content = f.read()
        exec(content, globals=globals())
        return lhs

# List operators

def create_list(anchor: Token, value: list[Expression]) -> Expression:
    res_properties = expand_property(anchor, 'list')
    res_properties[0].is_association = True
    res_properties[0].associated_value = value
    res = Expression(anchor, res_properties)
    return res

@builtin_defn
class ListAppendDefinition(Definition):
    symbol = 'append'
    property_names = ['appendable', 'collection']
    param_names = ['item']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        dst = lhs.try_get_property('collection')
        assert dst is not None
        dst.is_association = True
        dst.associated_value = dst.associated_value or []
        dst.associated_value.append(rhs)
        return rhs
    
@builtin_defn
class ListEachDefinition(Definition):
    symbol = 'each'
    property_names = ['iterable', 'collection']
    param_names = ['prev_placeholder', 'body']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        iterable = lhs.try_get_property('collection')
        assert iterable is not None 
        if iterable.associated_value is None:
            return lhs
        item_placeholder, body = args
        res: list[Expression] = []
        for item in iterable.associated_value:
            # item is an Expression
            from main import resolve_expr
            local_scope = Scope({item_placeholder.symbol.s: item}, parent_scope=scope)
            res.append(resolve_expr(body, local_scope))
        return create_list(lhs.symbol, res)

@builtin_defn
class ListIndexDefinition(Definition):
    symbol = 'index'
    property_names = ['indexable', 'collection']
    param_names = ['index']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        dst = lhs.try_get_property('collection')
        assert dst is not None
        if (isrc := rhs.try_get_property('integer')) is None:
            perror(f'unable to index {lhs} with {rhs}')
        if not isinstance(dst.associated_value, list) or \
                isrc.associated_value >= len(dst.associated_value):
            perror(f'index out of bounds on {lhs} with {rhs}')
        return dst.associated_value[isrc.associated_value]

# Logical operators

@builtin_defn
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
    
@builtin_defn
class PropertiesDefinition(Definition):
    symbol = 'properties'
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        res_list = []
        for p in lhs.properties:
            res_list.append(Expression(p.property, [
                Property(p.property.create_renamed('property'), is_association=True, associated_value=p)
            ]))
        return create_list(lhs.symbol, res_list)