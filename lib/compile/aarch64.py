if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, binary_apply, idempotent_apply, pwarning, CompileError

# We extend compilation
import llvmlite.ir as ir

if 'definitions' in globals():
    compile = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'lib/compile.py')
else:
    raise ImportError("definitions module not found, cannot import compile module")

class CompileAarch64GenericDefinition(Definition):
    symbol = 'compile'
    property_names: list[str]       # defined in subclasses
    arg_types: list[ir.Type] = []   # defined in subclasses
    instruction_template: str       # defined in subclasses
    input_constraints: str = ''     # optional, for inline assembly constraints

    def get_format_values(self, lhs: Expression, scope: Scope) -> list:
        return []
    def get_arg_values(self, lhs: Expression, scope: Scope) -> list[ir.Value]:
        raise NotImplementedError("get_arg_values must be implemented by subclasses")

    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        args = self.get_arg_values(lhs, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        asm_ty = ir.FunctionType(ir.VoidType(), self.arg_types)
        asm = ir.InlineAsm(
            asm_ty,
            self.instruction_template.format(*self.get_format_values(lhs, scope)),
            self.input_constraints,
            side_effect=True
        )
        builder.call(asm, args)
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=None)
        return lhs.replace_property('compile', compile_prop)

# System/interrupt instructions (Kernel Mode)

@builtin_definition
class CompileAarch64IretDefinition(CompileAarch64GenericDefinition):
    property_names = ['aarch64', 'eret']
    instruction_template = 'eret'
    def get_arg_values(self, lhs: Expression, scope: Scope) -> list[ir.Value]:
        return []
    
# System instructions (User Mode)
    

# Page table management instructions

# Move to TTBR0 TODO

# Move to TTBR1 TODO

@builtin_definition
class CompileAarch64TlbiPointerDefinition(CompileAarch64GenericDefinition):
    property_names = ['pointer', 'aarch64', 'tlbi']
    instruction_template = 'tlbi {0} ($0)'
    input_constraints = 'r'
    def get_format_values(self, lhs: Expression, scope: Scope) -> list:
        tlbi_prop = lhs.force_get_property('tlbi')
        if len(tlbi_prop.compound_properties) != 1:
            raise CompileError("Expected exactly one compound property for tlbi")
        tlbi_arg = tlbi_prop.compound_properties[0].symbol
        if tlbi_arg not in ['vae1', 'vae1is']:  # TODO more TLBI variants
            raise CompileError(f"Invalid tlbi argument: {tlbi_arg}")
        return [tlbi_arg]

    def get_arg_values(self, lhs: Expression, scope: Scope) -> list[ir.Value]:
        ptr_value = compile.get_compiled(lhs, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        ptr_value_ptr = builder.inttoptr(ptr_value, ir.PointerType(ir.IntType(64)))
        return [ptr_value_ptr]