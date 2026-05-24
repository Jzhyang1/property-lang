import logging
from typing import NoReturn
from constants import Expression, Property, Token, token_types

AnchorType = Expression|Property|Token|None
logging.basicConfig(format='[%(levelname)s %(name)s] %(message)s', level=logging.INFO)

def anchor_token(anchor: AnchorType) -> Token:
    if isinstance(anchor, Token):
        return anchor
    elif isinstance(anchor, Expression):
        return anchor.symbol
    elif isinstance(anchor, Property):
        return anchor.property
    else:
        return Token('<unknown>', '<unknown>', 0, 0, token_types['alnum'])
def is_warning(anchor: AnchorType) -> bool:
    if isinstance(anchor, Property):
        return anchor.property.s == 'warning'
    elif isinstance(anchor, Expression):
        return any(p.property.s == 'warning' for p in anchor.properties)
    else:
        return False

class CompileError(Exception):
    def __init__(self, message: str, anchor: AnchorType = None, child_error: Exception|AssertionError|None = None):
        self.message = message
        self.anchor = anchor
        self.child_error = child_error
        super().__init__(message)

def perror(*msg, anchor:AnchorType=None, child_error: Exception|AssertionError|None = None) -> NoReturn:
    token = anchor_token(anchor)
    header = f"{token.file}:{token.row}:{token.col}"
    message = '\n\t'.join(str(m) for m in msg)
    if (fix := suggest_fix(anchor)) is not None:
        message += '\n\n' + fix + '\n'
    logging.getLogger(header).exception(message, exc_info=child_error)
    raise CompileError(message, anchor=anchor, child_error=child_error)

def pwarning(*msg, anchor:AnchorType=None) -> Expression:
    token = anchor_token(anchor)
    placeholder_ret = Expression(token, [Property(token.create_renamed('warning'), is_association=True, associated_value=' '.join(str(m) for m in msg))])
    if is_warning(anchor):
        return placeholder_ret    # avoid duplicate warnings
    header = f"{token.file}:{token.row}:{token.col}"
    message = '\n\t'.join(str(m) for m in msg)
    if (fix := suggest_fix(anchor)) is not None:
        message += '\n\t' + fix
    logging.getLogger(header).warning(message)
    # For warnings, we return an empty expression so that the program can continue running, but the user is still informed of the issue
    return placeholder_ret

def suggest_fix(anchor: AnchorType) -> str|None:
    if anchor is None:
        return None
    elif isinstance(anchor, Token):
        return None
    elif isinstance(anchor, Property):
        return None
    elif isinstance(anchor, Expression):
        if anchor.try_get_property('identifier') is not None:
            return f"Try resolving `{anchor.symbol.s}` -> `{anchor.symbol.s}.`\n"
    return None