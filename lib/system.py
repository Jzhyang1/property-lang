import os
import sys
from constants import Expression, Property
from errors import pwarning
from definitions import register_definition

# TODO extend compilation

@register_definition('variable', ['system'], ['name'])
def get_system_variable(lhs: Expression, rhs: Expression) -> Expression:
    if (var := rhs.try_get_property('string')) is None:
        return pwarning(f"expected a string for variable name, got {rhs}", anchor=rhs)
    var_name = var.associated_value
    if var_name in os.environ:
        return Expression(lhs.symbol.create_renamed('variable'), [
            Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=os.environ[var_name])
        ])
    return pwarning(f"variable {var_name} not found in environment", anchor=rhs)

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
    os.dup2(new_stderr.associated_value.fileno(), sys.stderr.fileno())
    return lhs

@register_definition('assign', ['system', 'stdout'], ['value'])
def assign_stdout(lhs: Expression, rhs: Expression) -> Expression:
    if (new_stdout := rhs.try_get_property('file')) is None:
        return pwarning(f"expected a file for stdout, got {rhs}", anchor=rhs)
    os.dup2(new_stdout.associated_value.fileno(), sys.stdout.fileno())
    return lhs