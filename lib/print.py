from constants import Definition, Provenance, Scope, Expression, Property, Token
from definitions import register_definition, expression_to_associated_value
import definitions

# We extend compilation
import llvmlite.ir as ir

from errors import ErrorMessage, perror, pwarning
compile = definitions.import_module(Provenance.here(), 'compile.py')

@register_definition('print', ['format', 'string'], ['args...'])
def format_print(lhs: Expression, args: list[Expression]):
    fmt: str = lhs.force_get_property('string').associated_value
    raw_args = tuple(expression_to_associated_value(arg) for arg in args)
    try:
        s = fmt % raw_args
    except TypeError as e:
        # Count the format specifiers and get their types
        perror("Bad arguments {} for format specifier {}", raw_args, fmt, anchor=lhs, child_error=e)
    print(s)

@register_definition('print', ['list'])
def print_list(lhs: Expression) -> Expression:
    lval = lhs.force_get_property('list').associated_value
    print(lval)
    return lhs

# Compilation

# We only have the printf binding here, the rest is defined in lib/string.lang
@register_definition('print', ['compile', 'format', 'string'], ['args...'])
def compile_format_print(lhs: Expression, args: list[Expression], scope: Scope):
    builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
    module: ir.Module = compile.get_compile_construct(scope, '__MODULE__')
    fmt_arg: ir.Value = compile.get_compiled(lhs, scope)
    body_args: list[ir.Value] = [compile.get_compiled(arg, scope) for arg in args]
    res = builder.call(module.get_global('printf'), [fmt_arg] + body_args)
    # Flush immediately after
    builder.call(module.get_global('fflush'), [ir.Constant(ir.PointerType(ir.IntType(8)), None)])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
    return lhs.replace_property('compiled_result', compiled_prop)