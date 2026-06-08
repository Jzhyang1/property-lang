from constants import Definition, Provenance, Scope, Expression, Property, resolve
from errors import pwarning
from definitions import register_definition
import imports

# We extend compilation
import llvmlite.ir as ir
compile = imports.import_module(Provenance.here(), 'compile.py')

@register_definition('repeat', ['integer'], ['body...'])
def time_measure(lhs: Expression, body: list[Expression], scope: Scope):
    reps = lhs.force_get_property('integer').associated_value
    from main import expression_resolve_all
    for _ in range(reps):
        for expr in body:
            expression_resolve_all(expr, scope, resolve)
    return lhs

# Compile definitions