if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, pwarning, CompileError

# We extend compilation
import llvmlite.ir as ir
if 'definitions' in globals():
    compile = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'compile.py')
    cstdlib = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'compile/cstdlib.py')
else:
    raise ImportError("definitions module not found, cannot import compile module")


@builtin_definition
class PrintIntegerDefinition(Definition):
    symbol = 'print'
    property_names = ['integer']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        ival = lhs.try_get_property('integer')
        assert ival is not None
        print(ival.associated_value)
        return lhs

@builtin_definition
class PrintStringDefinition(Definition):
    symbol = 'print'
    property_names = ['string']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        sval = lhs.try_get_property('string')
        assert sval is not None
        print(sval.associated_value)
        return lhs
    
@builtin_definition
class PrintListDefinition(Definition):
    symbol = 'print'
    property_names = ['list']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        sval = lhs.try_get_property('list')
        assert sval is not None
        print(sval.associated_value)
        return lhs
    

# Compilation

def _define_print_integer(module):
    # Create a global string for the format specifier
    fmt_str = "%d\n\0"
    fmt_str_global = ir.GlobalVariable(module, ir.ArrayType(ir.IntType(8), len(fmt_str)), name="fmt_str")
    fmt_str_global.linkage = 'internal'
    fmt_str_global.global_constant = True
    fmt_str_global.initializer = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt_str)), bytearray(fmt_str.encode("utf8"))) # type: ignore

    # Define the print_integer function (returns its argument after printing it)
    print_integer_ty = ir.FunctionType(ir.IntType(64), [ir.IntType(64)])
    print_integer = ir.Function(module, print_integer_ty, name="print_integer")
    block = print_integer.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    fmt_arg = builder.bitcast(fmt_str_global, ir.PointerType(ir.IntType(8)))
    builder.call(module.get_global('printf'), [fmt_arg, print_integer.args[0]])
    builder.ret(print_integer.args[0])
    
compile.add_initializer(cstdlib.define_printf)
compile.add_initializer(cstdlib.define_puts)
compile.add_initializer(_define_print_integer)

@builtin_definition
class CompilePrintIntegerDefinition(Definition):
    symbol = 'compile'
    property_names = ['integer', 'print']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, _ = lhs.discard_properties_after('print')
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        lhs_val = compile.get_compiled(lhs, scope)
        print_res = builder.call(compile.get_compile_construct(scope, '__MODULE__').get_global('print_integer'), [lhs_val], 'print_tmp')
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=lhs_val)
        return lhs.replace_property('compile', compile_prop)

@builtin_definition
class CompilePrintStringDefinition(Definition):
    symbol = 'compile'
    property_names = ['string', 'print']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, _ = lhs.discard_properties_after('print')
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        lhs_val = compile.get_compiled(lhs, scope)
        puts = compile.get_compile_construct(scope, '__MODULE__').get_global('puts')
        str_arg = builder.inttoptr(lhs_val, ir.PointerType(ir.IntType(8)))
        print_res = builder.call(puts, [str_arg], 'print_tmp')
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=lhs_val)
        return lhs.replace_property('compile', compile_prop)
