from typing import Callable

import llvmlite.ir as ir
import llvmlite.binding as llvm

if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token, expand_property
    from definitions import builtin_defn, binary_apply, pwarning, perror

llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

CompileScope = dict[str, ir.GlobalVariable]

binary_ops = {
    'assign': ('store'),
    '+': ('add'),
    '<': ('cmp_unordered'),
}

unary_ops = {
    'print': ('print'),
    'logical_not': ('logical_not'),
}

def _define_print_integer(module):
    # Add the declaration of printf to the module
    printf_ty = ir.FunctionType(ir.IntType(32), [ir.PointerType(ir.IntType(8))], var_arg=True)
    printf = ir.Function(module, printf_ty, name="printf")

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
    builder.call(printf, [fmt_arg, print_integer.args[0]])
    builder.ret(print_integer.args[0])

def _compile_expression(expression: Expression, scope: CompileScope,
                       module: ir.Module, builder: ir.builder.IRBuilder, evaluate=False):
    if len(expression.properties) > 0 and expression.properties[-1].property == '.':
        return _compile_expression(
            Expression(expression.symbol, expression.properties[:-1]),
            scope, module, builder, True
        )
    if not evaluate:
        # for now we only allow 1 association property on a symbol
        if (val:=expression.try_get_property('integer')):
            # TODO integer sizes can vary with properties
            return ir.Constant(ir.IntType(64), val.associated_value or 0)
        elif (val:=expression.try_get_property('string')):
            perror('string compilation not implemented')
        else:
            perror(f'{expression} not resolved')
    else:
        *properties, p = expression.properties
        if p.property == 'identifier':
            return scope[expression.symbol.s]
        elif p.property.s in binary_ops:
            lhs = _compile_expression(
                Expression(expression.symbol, properties),
                scope, module, builder
            )
            rhs = _compile_expression(
                p.compound_properties[0],
                scope, module, builder
            )
            # TODO clean up a little
            if p.property == '+':
                return builder.add(lhs, rhs, 'add_tmp')
            elif p.property == '<':
                cmpres = builder.icmp_signed(p.property, lhs, rhs, 'cmp_tmp')
                # convert boolean to integer
                return builder.zext(cmpres, ir.IntType(64), 'bool_to_int_tmp')
            elif p.property == 'assign':
                return builder.store(rhs, lhs)
            else:
                perror(f"{expression} is not defined")
        elif p.property.s in unary_ops:
            val = _compile_expression(
                Expression(expression.symbol, properties),
                scope, module, builder
            )
            if p.property == 'print':
                return builder.call(module.get_global('print_integer'), [val], 'print_tmp')
            elif p.property == 'logical_not':
                zero = ir.Constant(ir.IntType(64), 0)
                cmpres = builder.icmp_signed('!=', val, zero, 'logical_not_tmp')
                return builder.zext(cmpres, ir.IntType(64), 'bool_to_int_tmp')
            else:
                perror(f"{expression} is not defined")
        elif p.property == 'resolution':
            perror("resolution definition not implemented")
        elif p.property == 'declare':
            # TODO allow non-integer types
            if not any(prop.property.s == 'integer' for prop in properties):
                perror('non-integer variables not implemented yet')
            scope[expression.symbol.s] = ir.GlobalVariable(module, ir.IntType(64), expression.symbol.s)
            return scope[expression.symbol.s]
        elif p.property == 'do':
            # compile everything in the body TODO the return value is inconsistent with the language
            last_val = None
            for expr in p.compound_properties:
                last_val = _compile_expression(expr, scope, module, builder)
            return last_val
        else:
            perror(f"User-defined resolution not implemented {expression}")


@builtin_defn
class CompileDefinition(Definition):
    symbol = 'compile'
    param_names = 'file_dest'
    @binary_apply
    def apply(self, lhs: Expression, file_dest: Expression, scope: Scope) -> Expression:
        module = ir.Module(lhs.symbol.file)
        target = llvm.Target.from_default_triple()
        target_machine = target.create_target_machine()
        module.triple = target_machine.triple
        module.data_layout = target_machine.target_data

        func = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="main")
        builder = ir.IRBuilder(func.append_basic_block(name="entry"))
        _define_print_integer(module)
        _compile_expression(lhs, {}, module, builder, True)
        builder.ret_void()

        if (path := file_dest.try_get_property('string')) is None:
            perror(f'compile destination must be a string, got {file_dest}')

        # Output compiled binary file
        llvm_ir = str(module)
        llvm_mod = llvm.parse_assembly(llvm_ir)
        llvm_mod.verify()

        if not path.associated_value.endswith('.o'):
            perror(f'compile destination must end with .o, got {file_dest}')

        with open(path.associated_value, 'wb') as f:
            f.write(target_machine.emit_object(llvm_mod))

        return lhs