import logging
from typing import NoReturn
from enum import Enum
from constants import Expression, Property, Provenance, ProvenanceAware, Token, Definition, token_types

logging.basicConfig(format='[%(levelname)s %(name)s] %(message)s', level=logging.INFO)

def is_warning(anchor: ProvenanceAware|None) -> bool:
    if isinstance(anchor, Property):
        return anchor.property.s == 'warning'
    elif isinstance(anchor, Expression):
        return any(p.property.s == 'warning' for p in anchor.properties)
    else:
        return False

class CompileError(Exception):
    def __init__(self, message: str, anchor: ProvenanceAware|None = None, child_error: Exception|AssertionError|None = None):
        self.message = message
        self.anchor = anchor
        self.child_error = child_error
        super().__init__(message)

class ErrorMessage(Enum):
    NO_IDENTIFIER = "cannot find identifier `{}`"
    NO_PATH = "unable to find path `{}`"
    NO_IMPORT_SYMBOL = "unable to import `{}` from `{}`"
    NO_PROPERTY = "unable to resolve `{}` on `{}`"
    MANY_DEFINITION = "cannot create definition `{}({})` that already exists"
    MANY_IMPORT_SYMBOL = "cannot import symbol `{}` that already exists"
    MANY_IMPORT_DEFINITION = "cannot import definition `{}({})` that already exists"
    MANY_MATCHES = "multiple matches found for `{}` on `{}`"
    BAD_TYPE = "attempting to use `{}` for `{}`"
    BAD_NUMBER_ARGS = "expected {} argument(s) to {} but got `{}`"
    BAD_COMPILE_EXTENSION = "compile destination `{}` must end with `.obj` or `.out`"
    BAD_INDEX = "Index {} out of bounds for list of size {}"
    BAD_SIZE = "Cannot have negative size {}"
    UNKNOWN_COMPILE_TIME = "Size of pointer must be known at compile time"
    UNOPEN_FILE = "file `{}` is not open"
    UNCLEARABLE_FILE = "unable to clear file `{}`"


def perror(message: ErrorMessage|str, *args, anchor: ProvenanceAware|None=None, child_error: Exception|None = None) -> NoReturn:
    source = anchor.get_source() if anchor else Provenance.caller()
    header = f"{source.file}:{source.row}:{source.col}"
    if isinstance(message, ErrorMessage):
        ret = message.value.format(*args)
        if (fix := suggest_fix(message, args, anchor)) is not None:
            ret += '\n\n' + fix + '\n'
    else:
        ret = message.format(*args)
    logging.getLogger(header).exception(ret, exc_info=child_error)
    raise CompileError(ret, anchor=anchor, child_error=child_error)

def pwarning(message: ErrorMessage|str, *args, anchor:ProvenanceAware|None=None) -> Expression:
    source = anchor.get_source() if anchor else Provenance.caller()
    header = f"{source.file}:{source.row}:{source.col}"
    if isinstance(message, ErrorMessage):
        ret = message.value.format(*args)
        if (fix := suggest_fix(message, args, anchor)) is not None:
            ret += '\n\n' + fix + '\n'
    else:
        ret = message.format(*args)
    if not is_warning(anchor):
        logging.getLogger(header).warning(ret)    # avoid duplicate warnings
    # For warnings, we return an empty expression so that the program can continue running, but the user is still informed of the issue
    token = Token('warning', source.file, source.row, source.col, token_types['alnum'])
    return Expression(token, [Property(token.create_renamed('warning'), is_association=True, associated_value=ret)])

def suggest_fix(message: ErrorMessage, args: list|tuple, anchor:ProvenanceAware|None) -> str|None:
    if message == ErrorMessage.NO_IDENTIFIER:
        return f"try replacing `{anchor}.` -> `{anchor}`"
    elif message == ErrorMessage.NO_PATH:
        return None
    elif message == ErrorMessage.NO_IMPORT_SYMBOL:
        return None
    elif message == ErrorMessage.NO_PROPERTY:
        return f"try replacing `{anchor}` -> `{anchor}.`"
    elif message == ErrorMessage.MANY_DEFINITION:
        return None
    elif message == ErrorMessage.MANY_IMPORT_SYMBOL:
        return None
    elif message == ErrorMessage.MANY_IMPORT_DEFINITION:
        return None
    elif message == ErrorMessage.MANY_MATCHES:
        return None
    elif message == ErrorMessage.BAD_TYPE:
        return None
    elif message == ErrorMessage.BAD_NUMBER_ARGS:
        return None
    elif message == ErrorMessage.BAD_COMPILE_EXTENSION:
        root = args[0][:args[0].rindex('.')]
        return f"try replacing {args[0]} with {root}.out or {root}.obj"
    elif message == ErrorMessage.BAD_INDEX:
        return None
    elif message == ErrorMessage.BAD_SIZE:
        return None
    elif message == ErrorMessage.UNKNOWN_COMPILE_TIME:
        return None
    elif message == ErrorMessage.UNOPEN_FILE:
        return None
    elif message == ErrorMessage.UNCLEARABLE_FILE:
        return None

    return None