if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import register_definition, CompileError

# We extend compilation
import llvmlite.ir as ir
if 'definitions' in globals():
    compile = globals()['definitions'].import_module(__file__, 'compile.py')
else:
    raise ImportError("definitions module not found, cannot import compile module")

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
    fmt_str = "%d\n\0"
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
    
compile.add_stdlib_definition(_define_print_integer)

@register_definition('print', ['compile', 'integer'])
def compile_print_integer(lhs: Expression, scope: Scope) -> Expression:
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    lhs_val = compile.get_compiled(lhs, scope)
    print_res = builder.call(compile.get_compile_construct(scope, '__MODULE__').get_global('print_integer'), [lhs_val], 'print_tmp')
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=lhs_val)
    return lhs.replace_property('compiled_result', compile_prop)

@register_definition('print', ['compile', 'string'])
def compile_print_string(lhs: Expression, scope: Scope) -> Expression:
    builder: ir.IRBuilder = compile.get_compile_construct(scope, '__BUILDER__')
    lhs_val = compile.get_compiled(lhs, scope)
    puts = compile.get_compile_construct(scope, '__MODULE__').get_global('puts')
    print_res = builder.call(puts, [lhs_val], 'print_tmp')
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=lhs_val)
    return lhs.replace_property('compiled_result', compile_prop)