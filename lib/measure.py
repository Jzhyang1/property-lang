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
    return lhs.replace_property('integer', Property(lhs.symbol.create_renamed('time_delta'), is_association=True, associated_value=time_delta_ns))

@register_definition('nanoseconds', ['timedelta'])
def int_nanosecond_time_delta(lhs: Expression) -> Expression:
    time_delta_ns = lhs.force_get_property('timedelta').associated_value
    return lhs.replace_property('timedelta', Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=time_delta_ns))

@register_definition('now', ['timestamp'])
def get_timestamp(lhs: Expression) -> Expression:
    # Our time is always in nonoseconds
    timestamp_ns = int(time.time() * 1e9)
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('timestamp'), is_association=True, associated_value=timestamp_ns))

@register_definition('-', ['timestamp'], [('start', ['timestamp'])])
def time_diff(lhs: Expression, rhs: Expression):
    timedelta_ns = lhs.force_get_property('timestamp').associated_value - rhs.force_get_property('timestamp').associated_value
    return lhs.replace_property('timestamp', Property(lhs.symbol.create_renamed('timedelta'), is_association=True, associated_value=timedelta_ns))

@register_definition('+', ['timestamp'], [('delta', ['timedelta'])])
def time_future(lhs: Expression, rhs: Expression):
    timestamp_ns = lhs.force_get_property('timestamp').associated_value + rhs.force_get_property('timedelta').associated_value
    return lhs.replace_property('timestamp', Property(lhs.symbol.create_renamed('timestamp'), is_association=True, associated_value=timestamp_ns))

@register_definition('measure', ['timedelta'], ['body...'])
def time_measure(lhs: Expression, body: list[Expression], scope: Scope):
    from main import expression_resolve_all
    start = time.time()
    for expr in body:
        expression_resolve_all(expr, scope, resolve)
    end = time.time()
    return lhs.replace_property('timedelta', Property(lhs.symbol.create_renamed('timedelta'), is_association=True, associated_value=int((end-start)*1e9)))

# Compile definitions

@register_definition('nanoseconds', ['compile', 'integer'])
def nanosecond_time_delta_compile(lhs: Expression) -> Expression:
    return lhs.replace_property('integer', Property(lhs.symbol.create_renamed('time_delta')))

@register_definition('nanoseconds', ['compile', 'timedelta'])
def int_nanosecond_time_delta_compile(lhs: Expression) -> Expression:
    return lhs.replace_property('timedelta', Property(lhs.symbol.create_renamed('integer')))

@register_definition('now', ['compile', 'timestamp'])
def get_timestamp_compile(lhs: Expression, scope: Scope) -> Expression:
    # Our time is always in nonoseconds
    builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
    module: ir.Module = compile.get_compile_construct(scope, '__MODULE__')
    get_time_func = module.get_global('timespec_get')
    # alloca a timespec struct on the stack
    timespec_struct = module.get_identified_types()['timespec_struct']
    timespec_ptr = builder.alloca(timespec_struct)
    # call timespec_get with the pointer to the timespec struct and the TIME_UTC constant (which is 1)
    builder.call(get_time_func, [timespec_ptr, ir.Constant(ir.IntType(32), 1)])
    # extract the seconds and nanoseconds from the timespec struct and combine them into a single nanosecond timestamp
    sec = builder.extract_value(builder.load(timespec_ptr), 0)
    nsec = builder.extract_value(builder.load(timespec_ptr), 1)
    timestamp_ns = builder.add(builder.mul(sec, ir.Constant(ir.IntType(64), 1000000000)), nsec)
    compiled_result = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=timestamp_ns)
    return lhs.replace_property('compiled_result', compiled_result)


@register_definition('-', ['timestamp'], ['compile', ('start', ['timestamp'])])
def time_diff_compile(lhs: Expression, rhs: Expression, scope: Scope):
    builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
    lhs_timestamp = compile.get_compiled(lhs, scope)
    rhs_timestamp = compile.get_compiled(rhs, scope)
    time_diff_ns = builder.sub(lhs_timestamp, rhs_timestamp)
    compiled_result = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=time_diff_ns)
    return lhs.replace_property('compiled_result', compiled_result).replace_property('timestamp', Property(lhs.symbol.create_renamed('timedelta')))


@register_definition('+', ['timestamp'], ['compile', ('delta', ['timedelta'])])
def time_future_compile(lhs: Expression, rhs: Expression, scope: Scope):
    builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
    lhs_timestamp = compile.get_compiled(lhs, scope)
    rhs_timedelta = compile.get_compiled(rhs, scope)
    future_timestamp_ns = builder.add(lhs_timestamp, rhs_timedelta)
    compiled_result = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=future_timestamp_ns)
    return lhs.replace_property('compiled_result', compiled_result)

# We implement `measure` in `measure.lang`
