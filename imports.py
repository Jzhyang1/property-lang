import inspect
import sys
import os
from typing import Any, Callable
from definitions import associated_value_to_expression, define_apply, expression_to_associated_value, get_defn_line, make_global_vars, register_definition
from errors import perror, pwarning, ErrorMessage

from constants import Definition, ProvenanceAware, Scope, Expression, Token, token_types

def _find_import_file(anchor: ProvenanceAware, path: str):
    path_relative = os.path.join(os.path.dirname(anchor.get_source().file), path)
    path_library = path
    if os.path.exists(path_relative):
        return path_relative
    elif os.path.exists(path_library):
        return path_library
    else:
        perror(f'unable to resolve path {path}', anchor=anchor)

# --------------------------------------------------
# imports on .lang files
# --------------------------------------------------

@register_definition('run', ['string'])
def run(lhs: Expression) -> Expression:
    path = lhs.force_get_property('string')
    path_str = _find_import_file(lhs, path.associated_value)
    from main import run_file
    run_file(path_str)
    return lhs

imported_files: dict[str, Scope] = {} # maps paths to global variable dicts, to avoid duplicate imports
@register_definition('import', ['string'], ['import_signatures...'])
def import_(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    path = lhs.force_get_property('string')
    path_str = _find_import_file(lhs, path.associated_value)
    if path_str in imported_files:
        imported_globals = imported_files[path_str]
    else:
        from main import run_file
        imported_globals = run_file(path_str)
        imported_files[path_str] = imported_globals
    for imported_symbol in body:
        symb = imported_symbol.symbol.s
        if symb in imported_globals.local_vars:
            scope.local_vars[symb] = imported_globals.local_vars[symb]
        elif symb in imported_globals.local_defns:
            scope.local_defns.setdefault(symb, []).extend(imported_globals.local_defns[symb])
        else:
            pwarning(ErrorMessage.NO_IMPORT_SYMBOL, symb, path_str, anchor=imported_symbol)
    return lhs


# --------------------------------------------------
# imports on dynamic library files
# --------------------------------------------------

class ImportedSharedDefinition(Definition):
    def __init__(self, name: str, is_compound: bool, func: Callable, source_file: str):
        # TODO somehow check the number of arguments of the function
        super().__init__(name, [], is_compound, [], [])
        self.func = func
    @define_apply
    def apply(self, lhs: Expression, args: list[Expression]) -> Expression:
        self_value = expression_to_associated_value(lhs)
        arg_values = [expression_to_associated_value(arg) for arg in args]
        res = self.func(self_value, *arg_values)
        return associated_value_to_expression(lhs.symbol, res)

@register_definition('import', ['string', 'shared'], ['import_signatures...'])
def import_shared(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    path = lhs.try_get_property('string')
    assert path is not None
    # Import the shared library file
    path_str = os.path.abspath(_find_import_file(lhs, path.associated_value))
    import ctypes
    lib = ctypes.CDLL(path_str)
    ## TODO signature definition
    for definition in body:
        symbol_name = definition.symbol.s
        defn_list = scope.local_defns.setdefault(symbol_name, [])
        defn_list.append(ImportedSharedDefinition(symbol_name, True, lib[symbol_name], path_str))
        defn_list.append(ImportedSharedDefinition(symbol_name, False, lib[symbol_name], path_str))
    return lhs


# --------------------------------------------------
# imports on .py files
# --------------------------------------------------

class ImportedPythonDefinition(Definition):
    def __init__(self, func: Callable, source_file: str):
        symbol = func.__name__
        # Get the parameters
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())
        _, *param_names = param_names
        def token(s: str):
            return Token(s, source_file, 0, 0, token_types['alnum']) # TODO better row accuracy
        super().__init__(symbol, [], 
                         len(param_names) > 0, [Expression(token(s), []) for s in param_names], [])
        self.func = func
    @define_apply
    def apply(self, lhs: Expression, args: list[Expression]) -> Expression:
        self_value = expression_to_associated_value(lhs)
        arg_values = [expression_to_associated_value(arg) for arg in args]
        res = self.func(self_value, *arg_values)
        return associated_value_to_expression(lhs.symbol, res)

def import_raw_python_file(anchor: Expression, path: str, imports: list[str], scope: Scope):
    path_str = _find_import_file(anchor, path)
    captured_globals: dict = make_global_vars(path_str)
    captured_globals['__file__'] = path_str
    with open(path_str, 'r') as f:
        content = f.read()
    # TODO make this safe
    code = compile(content, path_str, 'exec')
    exec(code, captured_globals)
    res = {}
    for symbol in imports:
        if symbol not in captured_globals:
            pwarning(ErrorMessage.NO_IMPORT_SYMBOL, symbol, path_str, anchor=anchor)
            continue
        defn_impl = captured_globals[symbol]
        if callable(defn_impl):
            scope.local_defns.setdefault(symbol, []).append(ImportedPythonDefinition(defn_impl, path_str))
        else:
            start_line = get_defn_line(defn_impl)
            scope.local_vars[symbol] = associated_value_to_expression(
                Token(symbol, path_str, start_line, 0, token_types['alnum']), defn_impl, symbol)
    return res
        

@register_definition('import', ['string', 'python'], ['import_signatures...'])
def import_python(lhs: Expression, body: list[Expression], scope: Scope) -> Expression:
    path = lhs.force_get_property('string')
    # Load in the python file
    import_raw_python_file(lhs, path.associated_value, [defn.symbol.s for defn in body], scope)
    return lhs

past_imports = {}
def import_module(anchor: ProvenanceAware, path_str: str):
    import importlib.util
    path_str = _find_import_file(anchor, path_str)
    # Get string from path_str
    module_name = os.path.splitext(os.path.basename(path_str))[0]

    spec = importlib.util.spec_from_file_location(module_name, path_str)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    # Check if we have already imported this module to avoid duplicates
    if module_name in past_imports: return past_imports[module_name]
    else: past_imports[module_name] = module

    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

@register_definition('import', ['string', 'python', 'definition'], ['import_signatures...'])
def import_python_definition(lhs: Expression) -> Expression:
    path = lhs.force_get_property('string')
    # Load in the python file
    import_module(lhs, path.associated_value)
    return lhs