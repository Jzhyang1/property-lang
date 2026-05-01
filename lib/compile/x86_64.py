if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, binary_apply, idempotent_apply, pwarning, CompileError

# We extend compilation
import llvmlite.ir as ir
if 'definitions' in globals():
    compile = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'lib/compile.py')
else:
    raise ImportError("definitions module not found, cannot import compile module")

class CompileX86_64GenericDefinition(Definition):
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
class CompileX86_64IretDefinition(CompileX86_64GenericDefinition):
    property_names = ['x86_64', 'iret']
    instruction_template = 'iret'
    def get_arg_values(self, lhs: Expression, scope: Scope) -> list[ir.Value]:
        return []
    
@builtin_definition
class CompileX86_64InterruptDefinition(CompileX86_64GenericDefinition):
    property_names = ['integer', 'x86_64', 'interrupt']
    instruction_template = 'int {0}'
    def get_format_values(self, lhs: Expression, scope: Scope) -> list:
        val = lhs.force_get_property('integer').associated_value
        assert isinstance(val, int), "Expected an integer value for interrupt number"
        return [val]
    
# System instructions (User Mode)

@builtin_definition
class CompileX86_64SyscallDefinition(CompileX86_64GenericDefinition):
    property_names = ['x86_64', 'syscall']
    instruction_template = 'syscall'
    def get_arg_values(self, lhs: Expression, scope: Scope) -> list[ir.Value]:
        return []
    

# Page table management instructions

@builtin_definition
class CompileX86_64MoveToCR3PointerDefinition(CompileX86_64GenericDefinition):
    property_names = ['pointer', 'x86_64', 'mov_to_cr3']
    instruction_template = 'mov cr3, $0'
    input_constraints = 'r'
    def get_arg_values(self, lhs: Expression, scope: Scope) -> list[ir.Value]:
        ptr_value = compile.get_compiled(lhs, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        ptr_value_ptr = builder.inttoptr(ptr_value, ir.PointerType(ir.IntType(64)))
        return [ptr_value_ptr]

@builtin_definition
class CompileX86_64InvlpgPointerDefinition(CompileX86_64GenericDefinition):
    property_names = ['pointer', 'x86_64', 'invlpg']
    instruction_template = 'invlpg ($0)'
    input_constraints = 'r'
    def get_arg_values(self, lhs: Expression, scope: Scope) -> list[ir.Value]:
        ptr_value = compile.get_compiled(lhs, scope)
        builder = compile.get_compile_construct(scope, '__BUILDER__')
        ptr_value_ptr = builder.inttoptr(ptr_value, ir.PointerType(ir.IntType(64)))
        return [ptr_value_ptr]