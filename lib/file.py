import io

from constants import Definition, Scope, Expression, Property, Token
from errors import pwarning
from definitions import register_definition
import definitions

# We extend compilation
import llvmlite.ir as ir
compile = definitions.import_module(__file__, 'compile.py')

@register_definition('file')
def file_property(lhs: Expression) -> Expression:
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('file')))

@register_definition('open', ['string', 'file'])
def open_file(lhs: Expression) -> Expression:
    file_prop = lhs.force_get_property('file')
    string_prop = lhs.force_get_property('string')
    file_prop.is_association = True
    file_prop.associated_value = open(string_prop.associated_value) # type: ignore
    return lhs.discard_property('string')

@register_definition('close', ['file'])
def close_file(lhs: Expression) -> Expression:
    file_prop = lhs.force_get_property('file')
    if not file_prop.is_association:
        return pwarning(f"cannot close file {file_prop} which is not open", anchor=lhs)
    file_prop.is_association = False
    file_prop.associated_value.close()
    return lhs

@register_definition('size', ['file'])
def size_file(lhs: Expression) -> Expression:
    file_prop = lhs.force_get_property('file')
    if not file_prop.is_association:
        return pwarning(f"cannot get size of file {file_prop} which is not open", anchor=lhs)
    position = file_prop.associated_value.tell()
    final_position = file_prop.associated_value.seek(0, io.SEEK_END)
    file_prop.associated_value.seek(position)    # Restore original position
    return Expression(lhs.symbol.create_renamed('size'), [
        Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=final_position)
    ])

@register_definition('read', ['file'])
def read_file(lhs: Expression) -> Expression:
    file_prop = lhs.force_get_property('file')
    if not file_prop.is_association:
        return pwarning(f"cannot read from file {file_prop} which is not open", anchor=lhs)
    return Expression(lhs.symbol.create_renamed('read'), [
        Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=file_prop.associated_value.read())
    ])


@register_definition('write', ['file'], ['string_to_write'])
def write_file(lhs: Expression, rhs: Expression) -> Expression:
    file_prop = lhs.force_get_property('file')
    if not file_prop.is_association:
        return pwarning(f"cannot write to file {file_prop} which is not open", anchor=lhs)
    if (rval := rhs.try_get_property('string')) is None:
        return pwarning(f"write requires a string property, got {rhs}", anchor=rhs)
    write_str: str = rval.associated_value # type: ignore
    file_prop.associated_value.write(write_str)
    return Expression(lhs.symbol.create_renamed('write'), [
        Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=write_str)
    ])


# Compilation

@register_definition('open', ['compile', 'string', 'file'])
def compile_open_file(lhs: Expression, scope: Scope) -> Expression:
    module = compile.get_compile_construct(scope, '__MODULE__')
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    fopen = module.get_global('fopen')
    filename = compile.get_compiled(lhs, scope)
    rw = compile.create_string('rw', scope)
    file_ptr = builder.call(fopen, [filename, rw], 'fopen_tmp')
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=file_ptr)
    return lhs.discard_property('string').replace_property('compiled_result', compile_prop)

@register_definition('close', ['compile', 'file'])
def compile_close_file(lhs: Expression, scope: Scope) -> Expression:
    module = compile.get_compile_construct(scope, '__MODULE__')
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    fclose = module.get_global('fclose')
    file_ptr = compile.get_compiled(lhs, scope)
    builder.call(fclose, [file_ptr])
    return lhs

@register_definition('size', ['compile', 'file'])
def compile_size_file(lhs: Expression, scope: Scope) -> Expression:
    module = compile.get_compile_construct(scope, '__MODULE__')
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    ftell = module.get_global('ftell')
    fseek = module.get_global('fseek')
    file_ptr = compile.get_compiled(lhs, scope)
    # Save current position
    current_pos = builder.call(ftell, [file_ptr], 'current_pos')
    # Seek to end to get size
    builder.call(fseek, [file_ptr, ir.Constant(ir.IntType(64), 0), ir.Constant(ir.IntType(32), io.SEEK_END)])
    size = builder.call(ftell, [file_ptr], 'file_size')
    size = builder.sext(size, ir.IntType(64), 'size_sext')
    # Restore original position
    builder.call(fseek, [file_ptr, current_pos, ir.Constant(ir.IntType(32), 0)])
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=size)
    return lhs.replace_property('compiled_result', compile_prop)

@register_definition('read', ['compile', 'file'])
def compile_read_file(lhs: Expression, scope: Scope) -> Expression:
    module = compile.get_compile_construct(scope, '__MODULE__')
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    malloc = module.get_global('malloc')
    fread = module.get_global('fread')

    buffer_size = compile.get_compiled(compile_size_file(lhs, scope), scope)
    buffer_size_plus_one = builder.add(buffer_size, ir.Constant(ir.IntType(64), 1), 'buffer_size_plus_one')
    buffer_ptr = builder.call(malloc, [buffer_size_plus_one], 'buffer_ptr')

    file_ptr = compile.get_compiled(lhs, scope)
    bytes_read = builder.call(fread, [buffer_ptr, ir.Constant(ir.IntType(64), 1), buffer_size, file_ptr], 'bytes_read')
    string_prop = Property(lhs.symbol.create_renamed('string'))
    compile_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=buffer_ptr)
    return lhs.replace_property('file', string_prop).replace_property('compiled_result', compile_prop)

@register_definition('write', ['compile', 'file'], ['string_to_write'])
def compile_write_file(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    module = compile.get_compile_construct(scope, '__MODULE__')
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    fwrite = module.get_global('fwrite')
    strlen = module.get_global('strlen')

    file_ptr = compile.get_compiled(lhs, scope)
    string_ptr = compile.get_compiled(rhs, scope)
    string_len = builder.call(strlen, [string_ptr], 'string_len')
    builder.call(fwrite, [string_ptr, ir.Constant(ir.IntType(64), 1), string_len, file_ptr])
    return lhs