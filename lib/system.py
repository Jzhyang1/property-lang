import os
import sys
from constants import Expression, Property
from errors import pwarning
from definitions import register_definition

# TODO extend compilation

# IO

@register_definition('variable', ['system'], ['name'])
def get_system_variable(lhs: Expression, rhs: Expression) -> Expression:
    var = rhs.force_get_property('string')
    var_name = var.associated_value
    val = os.environ.get(var_name, '')
    return Expression(lhs.symbol.create_renamed('variable'), [
        Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=val)
    ])

@register_definition('assign', ['system', 'variable'], ['value'])
def assign_system_variable(lhs: Expression, rhs: Expression) -> Expression:
    variable_prop = lhs.force_get_property('variable')
    if len(variable_prop.compound_properties) != 1:
        return pwarning(f"expected a variable, got {variable_prop}", anchor=lhs)
    variable_name = variable_prop.compound_properties[0]
    if (var := variable_name.try_get_property('string')) is None:
        return pwarning(f"expected a string for variable name, got {variable_name}", anchor=variable_name)
    if (value := rhs.try_get_property('string')) is None:
        return pwarning(f"expected a string for variable value, got {rhs}", anchor=rhs)
    os.environ[var.associated_value] = value.associated_value
    return lhs

@register_definition('stdin', ['system'])
def get_stdin(lhs: Expression) -> Expression:
    return Expression(lhs.symbol.create_renamed('stdin'), [
        Property(lhs.symbol.create_renamed('file'), is_association=True, associated_value=sys.stdin)
    ])

@register_definition('stderr', ['system'])
def get_stderr(lhs: Expression) -> Expression:
    return Expression(lhs.symbol.create_renamed('stderr'), [
        Property(lhs.symbol.create_renamed('file'), is_association=True, associated_value=sys.stderr)
    ])

@register_definition('stdout', ['system'])
def get_stdout(lhs: Expression) -> Expression:
    return Expression(lhs.symbol.create_renamed('stdout'), [
        Property(lhs.symbol.create_renamed('file'), is_association=True, associated_value=sys.stdout)
    ])

@register_definition('assign', ['system', 'stdin'], ['value'])
def assign_stdin(lhs: Expression, rhs: Expression) -> Expression:
    if (new_stdin := rhs.try_get_property('file')) is None:
        return pwarning(f"expected a file for stdin, got {rhs}", anchor=rhs)
    os.dup2(new_stdin.associated_value.fileno(), sys.stdin.fileno())
    return lhs

@register_definition('assign', ['system', 'stderr'], ['value'])
def assign_stderr(lhs: Expression, rhs: Expression) -> Expression:
    if (new_stderr := rhs.try_get_property('file')) is None:
        return pwarning(f"expected a file for stderr, got {rhs}", anchor=rhs)
    sys.stderr.flush()  # Ensure all pending writes to stderr are flushed before redirecting
    os.dup2(new_stderr.associated_value.fileno(), sys.stderr.fileno())
    return lhs

@register_definition('assign', ['system', 'stdout'], ['value'])
def assign_stdout(lhs: Expression, rhs: Expression) -> Expression:
    if (new_stdout := rhs.try_get_property('file')) is None:
        return pwarning(f"expected a file for stdout, got {rhs}", anchor=rhs)
    if new_stdout.associated_value is None:
        return pwarning("Unopened file provided for stdout", anchor=rhs)
    sys.stdout.flush()  # Ensure all pending writes to stdout are flushed before redirecting
    os.dup2(new_stdout.associated_value.fileno(), sys.stdout.fileno())
    return lhs

# Paths

@register_definition('path', ['system'], ['path_str'])
def get_path(lhs: Expression, rhs: Expression) -> Expression:
    if (path_prop := rhs.try_get_property('string')) is None:
        return pwarning(f"expected a string for path, got {rhs}", anchor=rhs)
    path_str = path_prop.associated_value
    if not os.path.exists(path_str):
        return pwarning(f"path {path_str} does not exist", anchor=rhs)
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('path'), is_association=True, associated_value=path_str))

@register_definition('path', ['system', 'path'], ['extended_path_str'])
def extend_path(lhs: Expression, rhs: Expression) -> Expression:
    path_prop = lhs.force_get_property('path')
    if (extended_path_prop := rhs.try_get_property('string')) is None:
        return pwarning(f"expected a string for extended path, got {rhs}", anchor=rhs)
    extended_path_str = extended_path_prop.associated_value
    new_path = os.path.join(path_prop.associated_value, extended_path_str)
    if not os.path.exists(new_path):
        return pwarning(f"path {new_path} does not exist", anchor=rhs)
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('path'), is_association=True, associated_value=new_path))

@register_definition('list', ['system', 'path'], ['recursive...'])
def list_path(lhs: Expression, args: list[Expression]) -> Expression:
    path_prop = lhs.force_get_property('path')
    if not os.path.exists(path_prop.associated_value):
        return pwarning(f"path {path_prop.associated_value} does not exist", anchor=lhs)
    path = path_prop.associated_value
    if len(args) > 0:
        # Recursive listing
        all_files = []
        for root, dirs, files in os.walk(path):
            for name in files:
                all_files.append(os.path.join(root, name))
    else:
        all_files = [os.path.join(path, f) for f in os.listdir(path)]
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=[
        Expression(lhs.symbol.create_renamed('path'), [
            Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=f)
        ]) for f in all_files
    ]))