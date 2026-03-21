from constants import special_symbols, start_comment, end_comment, token_types, parentheses, separators, Property, Expression, Token

def tokenize(file) -> list[Token]:
    with open(file, 'r') as f:
        code = f.read()

    # split code when changing from alnum to special symbols or to spaces
    tokens: list[Token] = []
    current_token = ''
    row, col_start, col_end = 1, 1, 1
    current_type = token_types['space']

    for char in code:
        if current_type == token_types['string']:
            current_token += char
            if char == '"':
                # Terminate the string
                tokens.append(Token(current_token, file, row, col_start))
                current_token = ''
                current_type = token_types['space']
        elif char == '"':
            if current_type != token_types['space']:
                tokens.append(Token(current_token, file, row, col_start))
                col_start = col_end
                current_token = ''
            current_token += char
            current_type = token_types['string']
        elif char.isspace():
            if current_type != token_types['space']:
                # Only save if there was a token before
                tokens.append(Token(current_token, file, row, col_start))
                current_token = ''
                current_type = token_types['space']
            if char == '\n':
                row += 1
                col_end = 1
        elif char in special_symbols:
            if current_token and current_type != token_types['special_combined']:
                tokens.append(Token(current_token, file, row, col_start))
                col_start = col_end
                current_token = ''
            current_token += char
            current_type = token_types['special_combined']
        elif char.isalnum() or char == '_':
            if current_token and current_type != token_types['alnum']:
                tokens.append(Token(current_token, file, row, col_start))
                col_start = col_end
                current_token = ''
            current_token += char
            current_type = token_types['alnum']
        else:
            # For any other character, treat it as a single special symbol
            if current_type != token_types['space']:
                tokens.append(Token(current_token, file, row, col_start))
                col_start = col_end
                current_token = ''
                current_type = token_types['space']
            tokens.append(Token(char, file, row, col_start))
        col_end += 1
    if current_type != token_types['space']:
        tokens.append(Token(current_token, file, row, col_start))

    tokens_without_comments = []
    in_comment = False
    for token in tokens:
        if token == start_comment:
            in_comment = True
        elif token == end_comment:
            in_comment = False
        elif not in_comment:
            tokens_without_comments.append(token)

    return (tokens_without_comments)


def build_tree(tokens: list[Token], i=0, end_token=None) -> tuple[list[Expression], int]:
    # returns an array of tuples of (symbol, property array)
    # and property is of (is_compound, name, compound array)
    if tokens[i] == end_token:
        return [], i+1
    
    tree: list[Expression] = []
    symbol = None
    properties: list[Property] = []

    while i < len(tokens) and tokens[i] != end_token:
        if symbol is None:
            symbol = tokens[i]
            i += 1
            # different handling for integer, TODO string
            if symbol.s.isdigit():
                properties.append(Property(
                    symbol.create_renamed('integer'), 
                    is_association=True, associated_value=int(symbol.s)
                ))
            elif symbol.s.startswith('"') and symbol.s.endswith('"'):
                properties.append(Property(
                    symbol.create_renamed('string'),
                    # TODO eval is unsafe
                    is_association=True, associated_value=eval(symbol.s)
                ))
            elif symbol.s.isalnum():
                properties.append(Property(symbol.create_renamed('identifier')))
            else:
                properties.append(Property(symbol.create_renamed('operator')))
        elif tokens[i].s in parentheses:
            properties[-1].start_char = tokens[i].s
            properties[-1].is_compound = True
            compound_tree, i = build_tree(tokens, i+1, parentheses[tokens[i].s])
            properties[-1].compound_properties = compound_tree
        elif tokens[i].s in separators:
            properties.append(Property(tokens[i], False, []))
            tree.append(Expression(symbol, properties))
            # see if we can start a new symbol
            symbol = None
            properties = []
            i += 1
        else:
            properties.append(Property(tokens[i], False, []))
            i += 1
    if symbol:
        tree.append(Expression(symbol, properties))
    return tree, i+1