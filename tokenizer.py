import ast

from constants import special_symbols, start_comment, end_comment, token_types, parentheses, separators, Property, Expression, Token

def tokenize(file) -> list[Token]:
    with open(file, 'r') as f:
        code = f.read()

    # split code when changing from alnum to special symbols or to spaces
    tokens: list[Token] = []
    current_token = ''
    row, col_start, col_end = 1, 1, 1
    current_type = token_types['space']

    def push_token():
        nonlocal current_token, current_type, col_start, col_end
        if current_token:
            if current_type == token_types['alnum'] and current_token.isdigit():
                current_type = token_types['integer']
            tokens.append(Token(current_token, file, row, col_start, current_type))
            current_token = ''
            col_start = col_end
            current_type = token_types['space']

    for char in code:
        if current_type == token_types['string']:
            current_token += char
            if char == '"':
                # Terminate the string
                push_token()
        elif char == '"':
            if current_type != token_types['space']:
                push_token()
            current_token += char
            current_type = token_types['string']
        elif char.isspace():
            if current_type != token_types['space']:
                # Only save if there was a token before
                push_token()
            if char == '\n':
                row += 1
                col_end = 1
        elif char in special_symbols:
            if current_token and current_type != token_types['special_combined']:
                push_token()
            current_token += char
            current_type = token_types['special_combined']
        elif char.isalnum() or char == '_':
            if current_token and current_type != token_types['alnum']:
                push_token()
            current_token += char
            current_type = token_types['alnum']
        else:
            # For any other character, treat it as a single special symbol
            if current_type != token_types['space']:
                push_token()
            current_token = char
            current_type = token_types['special_single']
            push_token()
        col_end += 1
    if current_type != token_types['space']:
        push_token()

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


def build_tree_symbol(token: Token) -> Expression:
    if token.token_type == token_types['integer']:
        return Expression(token, [
            Property(token.create_renamed('integer'), is_association=True, associated_value=int(token.s))
        ])
    elif token.token_type == token_types['string']:
        return Expression(token, [
            Property(token.create_renamed('string'), is_association=True, associated_value=ast.literal_eval(token.s))
        ])
    elif token.token_type == token_types['alnum']:
        return Expression(token, [
            Property(token.create_renamed('identifier'))
        ])
    else:
        return Expression(token, [
            Property(token.create_renamed('operator'))
        ])

def build_tree(tokens: list[Token], i=0, end_token=None) -> tuple[list[Expression], int]:
    # returns an array of tuples of (symbol, property array)
    # and property is of (is_compound, name, compound array)
    if tokens[i] == end_token:
        return [], i+1
    
    tree: list[Expression] = []
    cur_expr: Expression | None = None

    while i < len(tokens) and tokens[i] != end_token:
        if cur_expr is None:
            cur_expr = build_tree_symbol(tokens[i])
            i += 1
        elif tokens[i].s in parentheses:
            prop = cur_expr.properties[-1]   # we modify the previous property
            prop.start_char = tokens[i].s
            prop.is_compound = True
            compound_tree, i = build_tree(tokens, i+1, parentheses[tokens[i].s])
            prop.compound_properties = compound_tree
            if prop.start_char == '[':
                # '[]' is an alias for '().'
                cur_expr.properties.append(Property(prop.property.create_renamed('.')))
        elif tokens[i].s in separators:
            cur_expr.properties.append(Property(tokens[i], False, []))
            tree.append(cur_expr)
            # see if we can start a new symbol
            cur_expr = None
            i += 1
        elif (tokens[i].token_type == token_types['special_combined'] and
              i+1 < len(tokens) and 
              tokens[i+1].token_type not in (token_types['special_single'], token_types['special_combined'])
              ):
            # peek ahead to see if we need to combine with the next token
            # this happens because operator followed by identifier/literal is an
            # alias for operator(identifier/literal.)
            arg_expr = build_tree_symbol(tokens[i+1])
            arg_expr.properties.append(Property(tokens[i+1].create_renamed('.')))

            cur_expr.properties.append(Property(tokens[i], True, [arg_expr], start_char='('))
            cur_expr.properties.append(Property(tokens[i+1].create_renamed('.')))
            i += 2  # we consumed two tokens
        else:
            # if len(properties) > 1 and not properties[-1].is_compound and
            cur_expr.properties.append(Property(tokens[i], False, []))
            i += 1
    if cur_expr is not None:
        tree.append(cur_expr)
    return tree, i+1