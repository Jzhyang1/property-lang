from typing import Any, Callable

special_symbols = set('~!@#$%^&*/-+=<>|?:')
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

class Token:
    def __init__(self, s: str, file: str, row: int, col: int, token_type: int):
        self.s = s
        self.file = file
        self.row = row
        self.col = col
        self.token_type = token_type
    def create_renamed(self, s: str):
        return Token(s, self.file, self.row, self.col, self.token_type)
    def __eq__(self, other: 'Token | str'):
        return str(other) == self.s
    def __str__(self) -> str:
        return self.s
    def __repr__(self) -> str:
        return f'[{self.file}:{self.row}:{self.col}] {self.s}'

class Property:
    def __init__(self, property: Token, 
                 is_compound: bool=False, compound_properties: list['Expression'] = [],
                 is_association: bool=False, associated_value: Any=None, start_char: str=''):
        self.property = property
        self.is_compound = is_compound
        self.compound_properties = compound_properties
        self.is_association = is_association
        self.associated_value = associated_value
        self.start_char = start_char
    def __str__(self) -> str:
        if self.is_association:
            return str(self.associated_value)
        return str(self.property) + (self.start_char or '?') + ','.join(map(str, self.compound_properties)) + parentheses.get(self.start_char, '?') if self.is_compound else str(self.property)
    def __repr__(self) -> str:
        return str(self)
    def copy(self):
        return Property(self.property, self.is_compound, self.compound_properties, self.is_association, self.associated_value, self.start_char)

class Expression:
    def __init__(self, symbol: Token, properties: list['Property']):
        self.symbol = symbol
        self.properties = properties
    def __str__(self) -> str:
        return str(self.symbol) + ':' + ' '.join(map(str, self.properties)) if len(self.properties) > 0 else str(self.symbol)
    def __repr__(self) -> str:
        return str(self)
    
    def try_get_property(self, property_name: str) -> Property | None:
        for property in self.properties:
            if property.property == property_name:
                return property
        return None
    def create_with_property(self, property: Property) -> 'Expression':
        new_expr = Expression(self.symbol, self.properties.copy())
        new_expr.properties.append(property)
        return new_expr

class Definition:
    def __init__(self, placeholder_symb: str, properties: list[Property], is_compound: bool, params: list[Expression], 
                 body: list[Expression]):
        self.placeholder_symb = placeholder_symb
        self.properties = properties
        self.is_compound = is_compound
        self.params = params
        self.body = body
    
    def apply(self, expr: Expression, args: list[Expression], scope: 'Scope', prop: Property) -> Expression:
        '''
        this is the function overloaded for builtin properties
        '''
        raise NotImplementedError()
    def __repr__(self):
        return str(self.placeholder_symb) + ':' + str(self.properties)

# Scoping
class Scope:
    def __init__(self, 
                 local_vars: None | dict[str, Expression] = None, local_defns: None | dict[str, list['Definition']] = None, 
                 parent_scope: 'None | Scope' = None):
        if local_vars is None: local_vars = {}
        if local_defns is None: local_defns = {}
        self.local_vars = local_vars
        self.local_defns = local_defns
        self.parent = parent_scope

    def var_lookup(self, var_name: str) -> Expression | None:
        return self.local_vars[var_name] if var_name in self.local_vars else \
            self.parent.var_lookup(var_name) if self.parent is not None else None
    def defn_lookup(self, var_name: str) -> list[Definition]:
        return self.local_defns[var_name] if var_name in self.local_defns else \
            self.parent.defn_lookup(var_name) if self.parent is not None else []
