import io
import os

from constants import Definition, Provenance, Scope, Expression, Property, Token
from errors import pwarning
from definitions import register_definition
import imports

# We extend compilation
import llvmlite.ir as ir
compile = imports.import_module(Provenance.here(), 'compile.py')

@register_definition('file')
def file_property(lhs: Expression, prop: Property) -> Expression:
    return lhs.create_with_property(prop)

@register_definition('copy', ['file'])
def assign_file(lhs: Expression) -> Expression:
    # We use os.dup to ensure we get a copy of the file descriptor
    file_prop = lhs.force_get_property('file')
    if not file_prop.is_association:
        return pwarning(f"cannot copy file {file_prop} which is not open", anchor=lhs)
    new_file = io.TextIOWrapper(io.FileIO(os.dup(file_prop.associated_value.fileno()), "a+"), write_through=True)
    new_file_prop = Property(lhs.symbol.create_renamed('file'), is_association=True, associated_value=new_file)
    return lhs.replace_property('file', new_file_prop)

@register_definition('open', ['string', 'file'])
def open_file(lhs: Expression) -> Expression:
    file_prop = lhs.force_get_property('file')
    string_prop = lhs.force_get_property('string')
    file_prop.is_association = True
    file_prop.associated_value = open(string_prop.associated_value, "a+") # type: ignore
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
    file_prop.associated_value.seek(0)  # Ensure we're at the start of the file
    read = file_prop.associated_value.read()
    return Expression(lhs.symbol.create_renamed('read'), [
        Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=read)
    ])


@register_definition('write', ['file'], [('string_to_write', ['string'])])
def write_file(lhs: Expression, rhs: Expression) -> Expression:
    file_prop = lhs.force_get_property('file')
    if not file_prop.is_association:
        return pwarning(f"cannot write to file {file_prop} which is not open", anchor=lhs)
    write_str: str = rhs.force_get_property('string').associated_value
    file_prop.associated_value.write(write_str)
    return Expression(lhs.symbol.create_renamed('write'), [
        Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=write_str)
    ])

@register_definition('clear', ['file'])
def clear_file(lhs: Expression) -> Expression:
    file_prop = lhs.force_get_property('file')
    if not file_prop.is_association:
        return pwarning(f"cannot clear file {file_prop} which is not open", anchor=lhs)
    try:
        file_prop.associated_value.seek(0)
        file_prop.associated_value.truncate()  # Clear the file contents
    except Exception as e:
        return pwarning(f"error while clearing file {file_prop}", anchor=lhs)
    return lhs

# Compilation

@register_definition('open', ['compile', 'string', 'file'])
def compile_open_file(lhs: Expression, scope: Scope) -> Expression:
    module = compile.get_compile_construct(scope, '__MODULE__')
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    fopen = module.get_global('fopen')
    filename = compile.get_compiled(lhs, scope)
    rw = compile.create_string('rw', scope)
    file_ptr = builder.call(fopen, [filename, rw], 'fopen_tmp')
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=file_ptr)
    return lhs.discard_property('string').replace_property('compiled_result', compiled_prop)

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
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=size)
    return lhs.replace_property('compiled_result', compiled_prop)

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
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=buffer_ptr)
    return lhs.replace_property('file', string_prop).replace_property('compiled_result', compiled_prop)

@register_definition('write', ['compile', 'file'], [('string_to_write', ['string'])])
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