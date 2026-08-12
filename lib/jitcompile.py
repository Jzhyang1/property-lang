from typing import Any

import llvmlite.binding as llvm
from llvmlite import ir
import ctypes
import ctypes.util

from constants import Definition, Expression, Property, Provenance, Scope, PropertiesLookup, PropertyContainerProtocol
from definitions import define_apply, expression_to_associated_value, associated_value_to_expression, register_definition, inherits
import imports
from errors import ErrorMessage, perror, pwarning
compile = imports.import_module(Provenance.here(), 'compile.py')

# Declare the signatures
def to_bytes(s: Any) -> bytes:
    if isinstance(s, str):
        return s.encode('utf-8')
    elif isinstance(s, int):
        return s.to_bytes(8, byteorder='little', signed=True)
    elif isinstance(s, list):
        # For lists, we can serialize them as a byte array of their elements' byte representations
        byte_array = bytearray()
        for item in s:
            item_bytes = to_bytes(item)
            byte_array.extend(to_bytes(len(item_bytes)))  # prefix with length
            byte_array.extend(item_bytes)
        # Add a null terminator for the list
        byte_array.extend(to_bytes(0))
        return byte_array
    else:
        raise TypeError(f"Cannot convert type {type(s)} to bytes")
    
def to_ctype(s: Any):
    if isinstance(s, str):
        return to_bytes(s)
    elif isinstance(s, int):
        return s
    else:
        perror("Please add to this line that threw the error {}", type(s))

class JITFunction(PropertyContainerProtocol):
    def __init__(self, cfunc, properties: list[Property]):
        self.cfunc = cfunc
        self.properties = properties

class GlobalJIT:
    symbols = [
        "malloc", "realloc", "free",
        "printf", "puts",
        "memcpy", "memset",
    ]
    def __init__(self):
        self.target = llvm.Target.from_default_triple()
        self.tm = self.target.create_target_machine()

        backing_mod = llvm.parse_assembly("")
        self.engine = llvm.create_mcjit_compiler(backing_mod, self.tm)

        self.modules: dict[str, llvm.ModuleRef] = {}
        self.compiled_funcs: dict[str, PropertiesLookup] = {}
        self.register_cstdlib_symbols()

    def add_module(self, module: ir.Module):
        if module.name in self.modules:
            pwarning(f"Module with name {module.name} already exists in JIT, skipping", anchor=None)
            return
        mod = llvm.parse_assembly(str(module))
        mod.verify()
        self.modules[module.name] = mod
        self.engine.add_module(mod)
        self.engine.finalize_object()
        # self.engine.run_static_constructors()

    def register_cstdlib_symbols(self):
        libc = ctypes.CDLL(ctypes.util.find_library("c"), mode=ctypes.RTLD_GLOBAL)
        for sym in GlobalJIT.symbols:
            llvm.add_symbol(
                sym,
                ctypes.cast(getattr(libc, sym), ctypes.c_void_p).value
            )
        # Also load in all existing imported_modules
        for module, funcs in compile.imported_modules.values():
            self.add_module(module)

    def find_llvm_func(self, llvm_func: ir.Function):
        cfunc = global_jit.engine.get_function_address(llvm_func.name)
        cfunc_ptr = ctypes.CFUNCTYPE(
            llvm_to_ctypes(llvm_func.return_value.type), 
            *[llvm_to_ctypes(param.type) for param in llvm_func.args]
        )(cfunc)
        return cfunc_ptr

global_jit = GlobalJIT()


CtypeOptions = type[ctypes._SimpleCData] | type[ctypes._Pointer] | type[ctypes.Structure]
def llvm_to_ctypes(llvm_type: ir.Type) -> CtypeOptions:
    """
    Returns the ctypes equivalent of a given llvmlite.ir.Type.
    """
    # Integer Types
    if isinstance(llvm_type, ir.IntType):
        if llvm_type.width == 64:
            return ctypes.c_int64
        elif llvm_type.width == 8:
            return ctypes.c_char
    # Void Types
    elif isinstance(llvm_type, ir.VoidType):
        return ctypes.c_void_p
    # Pointer Types
    elif isinstance(llvm_type, ir.PointerType):
        # void* for opaque or generic pointers
        pointee: ir.Type = llvm_type.pointee # type: ignore
        if isinstance(pointee, ir.VoidType):
            return ctypes.c_void_p
        # TODO we're just assuming all char arrays are strings which is dangerous
        elif isinstance(pointee, ir.IntType) and pointee.width == 8:
            return ctypes.c_char_p
        # recursively find the pointer base type
        return ctypes.POINTER(llvm_to_ctypes(pointee))
    # Array Types
    elif isinstance(llvm_type, ir.ArrayType):
        element_type = llvm_to_ctypes(llvm_type.element)
        return element_type * llvm_type.count
    # Structure Types
    elif isinstance(llvm_type, (ir.LiteralStructType, ir.IdentifiedStructType)):
        assert llvm_type.elements is not None
        fields = [llvm_to_ctypes(elem) for elem in llvm_type.elements]
        
        # Define a dynamic ctypes Structure
        class LLVMStruct(ctypes.Structure):
            _fields_ = [(f"f{i}", t) for i, t in enumerate(fields)]
        return LLVMStruct
    raise NotImplementedError(f"Cannot map LLVM type {type(llvm_type)} to ctypes")


class CompiledInterpretableUserDefinition(Definition):
    def __init__(self, prop_symb: str, properties: list[Property], is_compound: bool, params: list[Expression], scope: Scope|None, llvm_func: ir.Function, cfunc):
        super().__init__(prop_symb, properties, is_compound, params, [], scope)
        self.llvm_func = llvm_func
        self.true_param_types = [llvm_to_ctypes(param.type) for param in llvm_func.args]
        self.cfunc = cfunc
    @define_apply
    def apply(self, lhs: Expression, args: list[Expression]) -> Expression:
        # calls a compiled function in interpreter
        arg0_val = to_ctype(expression_to_associated_value(lhs))
        all_args = [to_ctype(expression_to_associated_value(arg)) for arg in args]
        arg_vals, vararg_vals = all_args[:len(self.params)], to_bytes(all_args[len(self.params):])
        varargs_ptr = (ctypes.c_char * len(vararg_vals)).from_buffer(vararg_vals)
        try:
            res = self.cfunc(arg0_val, *arg_vals, varargs_ptr)
        except ctypes.ArgumentError as e:
            perror("{}", e, anchor=lhs)
        return associated_value_to_expression(lhs.symbol, res)

class JITScope(Scope):
    def __init__(self, compile_scope: Scope, module: ir.Module):
        super().__init__()
        for name, defn_list in compile_scope.local_defns.items():
            jit_defn_list = defn_list
            for defn in defn_list:
                if not isinstance(defn, compile.CompiledUserDefinition):
                    continue
                non_compile_properties = [p for p in defn.properties if p.property.s != 'compile']
                func_name = compile.mangle_signature(name, non_compile_properties)
                llvm_func: ir.Function = module.get_global(func_name)
                cfunc_ptr = global_jit.find_llvm_func(llvm_func)
                jit_func = JITFunction(cfunc_ptr, non_compile_properties)
                # TODO What if we already have the function registered in JIT
                global_jit.compiled_funcs.setdefault(name, PropertiesLookup()).exprs.append(jit_func)
                imported_func = CompiledInterpretableUserDefinition(name, non_compile_properties, defn.is_compound, defn.params, defn.scope, llvm_func, cfunc_ptr)
                jit_defn_list.append(imported_func)
            self.local_defns[name] = jit_defn_list
        # TODO global values

@register_definition('import', ['jit', 'compile'], ['signatures...'])
def import_jit_compile(lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
    compile_scope = Scope(parent_scope=scope)
    expr: Expression = compile.compile_import(lhs.discard_property('jit'), args, compile_scope)
    # done compiling everything
    # JIT up all definitions in compile_scope
    module: ir.Module = expr.force_get_property('compiled_result').associated_value
    global_jit.add_module(module)
    imports.copy_these_from_scope(JITScope(compile_scope, module), scope, args, lhs)
    # Run the module once
    llvm_main: ir.Function = module.get_global(expr.symbol.s)
    global_jit.find_llvm_func(llvm_main)()
    return expr