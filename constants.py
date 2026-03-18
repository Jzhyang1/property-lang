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
}

parentheses = {
    '(': ')',
    '{': '}',
    '[': ']',
}

separators = {
    ',', ';'
}

# Used only by the interpreter internally
property_shorthands = {
    'list': ['collection', 'indexable', 'iterable', 'appendable']
}

class Token:
    def __init__(self, s: str, file: str, row: int, col: int):
        self.s = s
        self.file = file
        self.row = row
        self.col = col
    def create_renamed(self, s: str):
        return Token(s, self.file, self.row, self.col)
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

class Definition:
    def __init__(self, placeholder_symb: str, properties: list[Property], is_compound: bool, params: list[Expression], 
                 body: Expression):
        self.placeholder_symb = placeholder_symb
        self.properties = properties
        self.is_compound = is_compound
        self.params = params
        self.body = body
    
    def apply(self, expr: Expression, args: list[Expression], scope: 'Scope') -> Expression:
        '''
        this is the function overloaded for builtin properties
        '''
        raise NotImplementedError()
    def __repr__(self):
        return str(self.placeholder_symb) + ':' + str(self.properties)

# Scoping
VarScope = Callable[[str], 'Expression | None']
def local_varscope(local_dict: dict[str, 'Expression'], previous_scope: VarScope) -> VarScope:
    return lambda symbol: local_dict[symbol] if symbol in local_dict else previous_scope(symbol)

DefnScope = Callable[[str], list['Definition']]
def local_defnscope(local_dict: dict[str, list['Definition']], previous_scope: DefnScope) -> DefnScope:
    return lambda symbol: local_dict[symbol] if symbol in local_dict else previous_scope(symbol)

class Scope:
    def __init__(self, 
                 local_vars: None | dict[str, Expression] = None, local_defns: None | dict[str, list['Definition']] = None, 
                 parent_scope: 'None | Scope' = None):
        if local_vars is None: local_vars = {}
        if local_defns is None: local_defns = {}

        self.local_vars = local_vars
        self.local_defns = local_defns

        parent_var_lookup = parent_scope.var_lookup if parent_scope is not None else lambda x: None
        self.var_lookup = local_varscope(local_vars, parent_var_lookup)

        parent_defn_lookup = parent_scope.defn_lookup if parent_scope is not None else lambda x: []
        self.defn_lookup = local_defnscope(local_defns, parent_defn_lookup)

def expand_property(anchor: Token, shorthand: str) -> list[Property]:
    '''
    we always have the value-storing property at index 0
    '''
    return [Property(anchor.create_renamed(s)) for s in property_shorthands[shorthand]]