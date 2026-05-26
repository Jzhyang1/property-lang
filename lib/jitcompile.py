from typing import Any

import llvmlite.binding as llvm
from llvmlite import ir
import ctypes
import ctypes.util

from constants import Definition, Expression, Property, Scope, PropertiesLookup, PropertyContainerProtocol
from definitions import define_apply, expression_to_associated_value, associated_value_to_expression, register_definition
import definitions
from errors import pwarning
compile = definitions.import_module(__file__, 'compile.py')

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
        mod = llvm.parse_assembly(str(module))
        mod.verify()
        if mod.name in self.modules:
            pwarning(f"Module with name {mod.name} already exists in JIT, overwriting", anchor=None)
        self.modules[mod.name] = mod
        self.engine.add_module(mod)
        self.engine.finalize_object()
        self.engine.run_static_constructors()

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
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        # # calls a compiled function in interpreter
        # global_jit.engine.finalize_object()    # ensure the function is ready to be called
        # global_jit.engine.run_static_constructors()    # ensure any static constructors are run
        
        arg0_val = expression_to_associated_value(lhs)
        all_args = [expression_to_associated_value(arg) for arg in args]
        arg_vals, vararg_vals = all_args[:len(self.params)], to_bytes(all_args[len(self.params):])
        varargs_ptr = (ctypes.c_char * len(vararg_vals)).from_buffer(vararg_vals)
        res = self.cfunc(arg0_val, *arg_vals, varargs_ptr)
        return associated_value_to_expression(lhs.symbol, res)

@register_definition('import', ['jit', 'compile'], ['signatures...'])
def import_jit_compile(lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
    compile_scope = Scope(parent_scope=scope)
    expr: Expression = compile.compile_import(lhs.discard_property('jit'), args, compile_scope)
    # JIT up all definitions in compile_scope
    module: ir.Module = expr.force_get_property('compiled_result').associated_value
    global_jit.add_module(module)
    for arg in args:
        defn_lookup = compile_scope.defn_lookup_recursive(arg.symbol.s)
        defns = defn_lookup.list_all()
        if len(defns) == 0:
            return pwarning(f"No definitions found for symbol {arg.symbol.s} in compile scope")
        # TODO Only handle CompiledUserDefinitions that are not in GlobalJIT yet 
        for defn in defns:
            if not isinstance(defn, compile.CompiledUserDefinition):
                continue
            symb, non_compile_properties = defn.prop_symb, defn.properties
            for i, prop in enumerate(defn.properties):
                if prop.property == 'compile':
                    non_compile_properties = defn.properties[:i] + defn.properties[i+1:]
                    break
            cfunc_lookup = global_jit.compiled_funcs.get(symb)
            _, existing_cfunc = cfunc_lookup.lookup(non_compile_properties, []) if cfunc_lookup else (-1, None)
            if existing_cfunc and len(existing_cfunc.properties) == len(non_compile_properties):
                # TODO this may be a bit hacky if there are repeated properties, but we must do unordered comparison and this is the easiest
                # Although there is no name mangling yet so the case of overriding a past definition is undefined behavior anyway
                pwarning(f"JIT definition for '{symb}' with properties {non_compile_properties} already exists", anchor=arg)
                continue
            cfunc = global_jit.engine.get_function_address(symb)
            llvm_func: ir.Function = module.get_global(symb)
            # TODO return non-int
            cfunc_ptr = ctypes.CFUNCTYPE(ctypes.c_int64, *[llvm_to_ctypes(param.type) for param in llvm_func.args])(cfunc)
            jit_func = JITFunction(cfunc_ptr, non_compile_properties)
            global_jit.compiled_funcs.setdefault(symb, PropertiesLookup()).exprs.append(jit_func)
            
            # Create CompiledInterpretableUserDefinition
            idefn = CompiledInterpretableUserDefinition(symb, non_compile_properties, defn.is_compound, defn.params, defn.scope, llvm_func, cfunc_ptr)
            scope.local_defns.setdefault(symb, []).append(idefn)
    return expr