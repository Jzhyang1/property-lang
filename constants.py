from abc import abstractmethod
from dataclasses import dataclass
import inspect
from typing import Any, Callable, overload

special_symbols = set('~@#$%^&*/-+=<>|?:')
start_comment = '/*'
end_comment = '*/'

token_types = {
    'space': -1,
    'special_single': 0,
    'special_combined': 1,
    'alnum': 2,
    'string': 3,
    'integer': 4,
}

parentheses = {
    '(': ')',
    '{': '}',
    '[': ']',
}

separators = {
    ',', ';'
}

immediate_resolve = ['!']
resolve = ['.'] + immediate_resolve

class ProvenanceAware:
    @abstractmethod
    def get_source(self) -> 'Provenance':
        pass

@dataclass
class Provenance(ProvenanceAware):
    file: str
    row: int
    col: int
    def get_source(self) -> 'Provenance':
        return self
    @classmethod
    def here(cls)->'Provenance':
        '''returns the location where this method is called'''
        parent = inspect.stack()[1]
        return Provenance(parent.filename, parent.lineno, parent.index or 0)
    @classmethod
    def caller(cls)->'Provenance':
        '''returns the location where this method is called'''
        parent = inspect.stack()[2]
        return Provenance(parent.filename, parent.lineno, parent.index or 0)

class Token(ProvenanceAware):
    def __init__(self, s: str, file: str, row: int, col: int, token_type: int):
        self.s = s
        self.file = file
        self.row = row
        self.col = col
        self.token_type = token_type
    def create_renamed(self, s: str):
        return Token(s, self.file, self.row, self.col, self.token_type)
    def get_source(self) -> Provenance:
        return Provenance(self.file, self.row, self.col)
    def __eq__(self, other: 'Token | str'):
        return str(other) == self.s
    def __str__(self) -> str:
        return self.s
    def __repr__(self) -> str:
        return f'[{self.file}:{self.row}:{self.col}] {self.s}'

class Property(ProvenanceAware):
    def __init__(self, property: Token, 
                 is_compound: bool=False, compound_properties: list['Expression']|None = None,
                 is_association: bool=False, associated_value: Any=None, start_char: str=''):
        self.property = property
        self.is_compound = is_compound
        self.compound_properties = compound_properties or []
        self.is_association = is_association
        self.associated_value = associated_value
        self.start_char = start_char
    def __str__(self) -> str:
        return str(self.property) + (self.start_char or '?') + ','.join(map(str, self.compound_properties)) + parentheses.get(self.start_char, '?') if self.is_compound else str(self.property)
    def __repr__(self) -> str:
        return str(self)
    def get_source(self) -> Provenance:
        return self.property.get_source()
    def copy(self):
        return Property(self.property, self.is_compound, self.compound_properties, self.is_association, self.associated_value, self.start_char)

class PropertyContainerProtocol:    # Protocol
    properties: list[Property]

class Expression(PropertyContainerProtocol, ProvenanceAware):
    def __init__(self, symbol: Token, properties: list['Property']):
        self.symbol = symbol
        self.properties = properties
    def __str__(self) -> str:
        return str(self.symbol) + ':' + ' '.join(map(str, self.properties)) if len(self.properties) > 0 else str(self.symbol)
    def __repr__(self) -> str:
        return str(self)
    def get_source(self) -> Provenance:
        return self.symbol.get_source()
    def copy(self):
        return Expression(self.symbol, [property.copy() for property in self.properties])
    def try_get_property(self, property_name: str) -> Property | None:
        for property in self.properties:
            if property.property == property_name:
                return property
        return None
    def force_get_property(self, property_name: str) -> Property:
        prop = self.try_get_property(property_name)
        assert prop is not None
        return prop
    def create_with_property(self, property: Property) -> 'Expression':
        new_expr = Expression(self.symbol, self.properties.copy())
        new_expr.properties.append(property)
        return new_expr
    def replace_property(self, to_replace: str, new_property: Property) -> 'Expression':
        '''
        removes any previous properties with the same name as to_replace, then
        prepends new_property to the properties list
        '''
        new_expr = Expression(self.symbol, [property for property in self.properties if property.property != to_replace])
        new_expr.properties.insert(0, new_property)
        return new_expr
    def discard_properties_after(self, prop_str: str) -> tuple['Expression', Property]:
        '''
        pops properties from the end of expr until it finds a property with the given name
        returns the expression remaining, the property with the given name
        '''
        i = len(self.properties) - 1
        properties = self.properties
        while i >= 0 and properties[i].property.s != prop_str:
            i -= 1
        if i < 0:
            raise Exception(f"property {prop_str} not found in expression {self}")
        return Expression(self.symbol, properties[:i]), properties[i]
    def discard_property(self, prop_str: str, all_occurrences: bool = False) -> 'Expression':
        '''
        removes the first property with the given name from the properties list
        if all_occurrences is True, removes all properties with the given name
        '''
        if all_occurrences:
            new_props = [property for property in self.properties if property.property.s != prop_str]
        else:
            new_props = [property for property in self.properties]
            for i in range(len(new_props)):
                if new_props[i].property.s == prop_str:
                    new_props.pop(i)
                    break
        new_expr = Expression(self.symbol, new_props)
        return new_expr
    
    def pop_properties_after(self, prop_str: str) -> tuple['Expression', list[Property]|None]:
        '''
        pops properties from the end of expr until it finds a property with the given name
        returns the expression remaining, the properties popped (excluding the property with the given name)
        '''
        i = len(self.properties) - 1
        properties = self.properties
        while i >= 0 and properties[i].property.s != prop_str:
            i -= 1
        if i < 0:
            return self, None
        return Expression(self.symbol, properties[:i+1]), properties[i+1:]

class Definition(PropertyContainerProtocol, ProvenanceAware):
    trace_stack: list[tuple[Expression, list[Expression], 'Scope', Property]] = []
    def __init__(self, prop_symb: str, properties: list[Property], is_compound: bool, params: list[Expression], 
                 body: list[Expression], scope: 'Scope|None' = None,
                 def_file: str = '<unknown>', def_row: int = 0):
        self.prop_symb = prop_symb
        self.properties = properties
        self.is_compound = is_compound
        self.params = params
        self.body = body
        self.scope = scope
        self.def_file = def_file
        self.def_row = def_row

    def apply(self, expr: Expression, args: list[Expression], scope: 'Scope', prop: Property) -> Expression:
        '''
        this is the function overloaded for builtin properties
        '''
        raise NotImplementedError()
    def __repr__(self):
        func_name = ' '.join(p.property.s for p in self.properties) + ' ' + self.prop_symb
        return f'[{func_name}]({self.def_file}:{self.def_row})'
    def get_source(self) -> Provenance:
        return Provenance(self.def_file, self.def_row, 0)
    def as_expression(self) -> Expression:
        tok = Token(self.prop_symb, self.def_file, self.def_row, 0, token_types['alnum'])
        return Expression(tok, self.properties)
    
# For fast Python prototyping
type PropertyLiteral = 'str|tuple[str,list[ExpressionLiteral]]'
type ExpressionLiteral = 'str|tuple[str,list[PropertyLiteral]]'
def literal_pack_to_property(props: list[PropertyLiteral], anchor: ProvenanceAware)->list[Property]:
    source = anchor.get_source()
    res = []
    for prop in props:
        s, l = (prop, []) if isinstance(prop, str) else prop
        if s.endswith('...'):
            # TODO type handling for variadic parameters(?)
            continue
        token = Token(s, source.file, source.row, source.col, token_types['alnum'])
        exprs = literal_pack_to_expression(l, anchor)
        res.append(Property(token, is_compound=len(exprs)>0, compound_properties=exprs))
    return res
def literal_pack_to_expression(exprs: list[ExpressionLiteral], anchor: ProvenanceAware)->list[Expression]:
    source = anchor.get_source()
    res = []
    for expr in exprs:
        s, l = (expr, []) if isinstance(expr, str) else expr
        if s.endswith('...'):
            # TODO type handling for variadic parameters(?)
            continue
        token = Token(s, source.file, source.row, source.col, token_types['alnum'])
        props = literal_pack_to_property(l, anchor)
        res.append(Expression(token, properties=props))
    return res


# Scoping
class PropertiesLookup[T: PropertyContainerProtocol]:
    def __init__(self, exprs: list[T] = [], parent_lookup: 'PropertiesLookup|None' = None):
        self.exprs = exprs
        self.parent_lookup = parent_lookup
    def __get_best_score(self, prop_scores: dict[str, int]) -> tuple[int, T|None]:
        best_score, best = -1, None
        for expr in self.exprs:
            # TODO 1<<32 is a magic number that is meant to mean "all mismatches are disallowed"
            score = sum(prop_scores.get(prop.property.s, -(1<<32)) for prop in expr.properties)
            if score > best_score:
                best_score, best = score, expr
        if self.parent_lookup is not None:
            parent_score, parent_best = self.parent_lookup.__get_best_score(prop_scores)
            if parent_score > best_score:
                return parent_score, parent_best
            elif parent_score == best_score:
                return parent_score, None
        return best_score, best
            
    def lookup(self, expr_props: list[Property], additional_props: list[Property]) -> tuple[int, T|None]:
        '''returns (score, match), where there are no match options if score < 0'''
        # Given lists of properties X and Y, find the expression Z in self.exprs that best matches X
        # The "best match" for X and Y is:
        # 1. Z matches as many properties in Y as possible
        # 2. Z matches the last property in X; if none or multiple such Z exist, compare those to the next-to-last property in X, etc.
        prop_scores = {}
        for i, prop in enumerate(expr_props):
            prop_scores[prop.property.s] = 1 << i
        for i, prop in enumerate(additional_props):
            prop_scores[prop.property.s] = 1 << len(expr_props)
        score, best = self.__get_best_score(prop_scores)
        return score, best
    def list_all(self, existing: list[T]|None = None) -> list[T]:
        existing = existing or []
        existing.extend(self.exprs.copy())
        if self.parent_lookup is not None:
            self.parent_lookup.list_all(existing)
        return existing

class Scope:
    def __init__(self, 
                 local_vars: None|dict[str, Expression] = None, local_defns: None|dict[str, list['Definition']] = None, 
                 parent_scope: 'None|Scope' = None, is_global: bool=False):
        if local_vars is None: local_vars = {}
        if local_defns is None: local_defns = {}
        self.local_vars = local_vars
        self.local_defns = local_defns
        self.parent = parent_scope
        self.is_global = is_global

    def var_lookup(self, var_name: str) -> Expression | None:
        return self.local_vars[var_name] if var_name in self.local_vars else \
            self.parent.var_lookup(var_name) if self.parent is not None else None
    def defn_lookup_recursive(self, var_name: str) -> PropertiesLookup[Definition]:
        if var_name not in self.local_defns and self.parent is not None:
            return self.parent.defn_lookup_recursive(var_name)
        local_found = self.local_defns[var_name] if var_name in self.local_defns else []
        parent_lookup = self.parent.defn_lookup_recursive(var_name) if self.parent is not None else None
        return PropertiesLookup(local_found, parent_lookup=parent_lookup)
    def force_var_lookup(self, var_name: str) -> Expression:
        var = self.var_lookup(var_name)
        assert var is not None
        return var
    
    def __str__(self) -> str:
        s = "Global" if self.is_global else "Scope"
        return f'{s}(vars={self.local_vars}, defns={self.local_defns}, parent={self.parent})'