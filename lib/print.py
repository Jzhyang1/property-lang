from constants import Definition, Provenance, Scope, Expression, Property, Token
from definitions import register_definition
import definitions

# We extend compilation
import llvmlite.ir as ir
compile = definitions.import_module(Provenance.here(), 'compile.py')

@register_definition('print', ['integer'])
def print_integer(lhs: Expression) -> Expression:
    ival = lhs.force_get_property('integer')
    print(ival.associated_value)
    return lhs

@register_definition('print', ['string'])
def print_string(lhs: Expression) -> Expression:
    sval = lhs.force_get_property('string')
    print(sval.associated_value)
    return lhs

@register_definition('print', ['list'])
def print_list(lhs: Expression) -> Expression:
    lval = lhs.force_get_property('list')
    print(lval.associated_value)
    return lhs

# Compilation

def _define_print_integer(module):
    # Create a global string for the format specifier
    fmt_str = "%ld\n\0"
    fmt_ty = ir.ArrayType(ir.IntType(8), len(fmt_str))
    fmt_str_global = ir.GlobalVariable(module, fmt_ty, name="fmt_str")
    fmt_str_global.linkage = 'internal'
    fmt_str_global.global_constant = True
    fmt_str_global.initializer = ir.Constant(fmt_ty, bytearray(fmt_str.encode("utf8"))) # type: ignore

    # Define the print_integer function (returns its argument after printing it)
    print_integer = ir.Function(module, ir.FunctionType(ir.IntType(64), [ir.IntType(64)]), name="print_integer")
    block = print_integer.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    fmt_arg = builder.bitcast(fmt_str_global, ir.PointerType(ir.IntType(8)))
    builder.call(module.get_global('printf'), [fmt_arg, print_integer.args[0]])
    builder.ret(print_integer.args[0])

def _define_flush_all(module):
    flush = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="flush")
    block = flush.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    builder.call(module.get_global('fflush'), [ir.Constant(ir.PointerType(ir.IntType(8)), None)])
    builder.ret_void()
    
compile.add_stdlib_definition(_define_print_integer)
compile.add_stdlib_definition(_define_flush_all)

@register_definition('print', ['compile', 'integer'])
def compile_print_integer(lhs: Expression, scope: Scope) -> Expression:
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')
    lhs_val = compile.get_compiled(lhs, scope)
    builder.call(module.get_global('print_integer'), [lhs_val], 'print_tmp')
    builder.call(module.get_global('flush'), [])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=lhs_val)
    return lhs.replace_property('compiled_result', compiled_prop)

@register_definition('print', ['compile', 'string'])
def compile_print_string(lhs: Expression, scope: Scope) -> Expression:
    builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')
    lhs_val = compile.get_compiled(lhs, scope)
    builder.call(module.get_global('puts'), [lhs_val], 'print_tmp')
    builder.call(module.get_global('flush'), [])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=lhs_val)
    return lhs.replace_property('compiled_result', compiled_prop)

@register_definition('print', ['compile', 'pointer'])
def compile_print_pointer(lhs: Expression, scope: Scope) -> Expression:
    # For now we just print the pointer as an integer, but ideally we would want to print hex
    builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')
    lhs_val = compile.get_compiled(lhs, scope)
    lhs_val_int = builder.ptrtoint(lhs_val, ir.IntType(64))
    builder.call(module.get_global('print_integer'), [lhs_val_int], 'print_tmp')
    builder.call(module.get_global('flush'), [])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=lhs_val)
    return lhs.replace_property('compiled_result', compiled_prop)