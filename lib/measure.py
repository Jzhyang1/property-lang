import time

from constants import Definition, Provenance, Scope, Expression, Property, resolve
from errors import pwarning
from definitions import register_definition
import imports

# We extend compilation
import llvmlite.ir as ir
compile = imports.import_module(Provenance.here(), 'compile.py')

@register_definition('timestamp')
def timestamp_property(lhs: Expression, prop: Property) -> Expression:
    return lhs.create_with_property(prop)

@register_definition('timedelta')
def timedelta_property(lhs: Expression, prop: Property) -> Expression:
    return lhs.create_with_property(prop)

@register_definition('nanoseconds', ['integer'])
def nanosecond_time_delta(lhs: Expression) -> Expression:
    time_delta_ns = lhs.force_get_property('integer').associated_value
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('time_delta'), is_association=True, associated_value=time_delta_ns))

@register_definition('nanoseconds', ['timedelta'])
def int_nanosecond_time_delta(lhs: Expression) -> Expression:
    time_delta_ns = lhs.force_get_property('timedelta').associated_value
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=time_delta_ns))

@register_definition('now', ['timestamp'])
def get_timestamp(lhs: Expression) -> Expression:
    # Our time is always in nonoseconds
    timestamp_ns = int(time.time() * 1e9)
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('timestamp'), is_association=True, associated_value=timestamp_ns))

@register_definition('-', ['timestamp'], [('start', ['timestamp'])])
def time_diff(lhs: Expression, rhs: Expression):
    timedelta_ns = lhs.force_get_property('timestamp').associated_value - rhs.force_get_property('timestamp').associated_value
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('timedelta'), is_association=True, associated_value=timedelta_ns))

@register_definition('+', ['timestamp'], [('delta', ['timedelta'])])
def time_future(lhs: Expression, rhs: Expression):
    timestamp_ns = lhs.force_get_property('timestamp').associated_value + rhs.force_get_property('timedelta').associated_value
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('timestamp'), is_association=True, associated_value=timestamp_ns))

@register_definition('measure', ['timedelta'], ['body...'])
def time_measure(lhs: Expression, body: list[Expression], scope: Scope):
    from main import expression_resolve_all
    start = time.time()
    for expr in body:
        expression_resolve_all(expr, scope, resolve)
    end = time.time()
    return lhs.replace_property('timedelta',
                                Property(lhs.symbol.create_renamed('timedelta'), is_association=True, associated_value=int((end-start)*1e9)))

# Compile definitions