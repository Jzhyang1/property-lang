from constants import Definition, Scope, Expression, Property, Token
from definitions import register_definition, pwarning, CompileError

@register_definition('file')
def file_property(lhs: Expression) -> Expression:
    return lhs.create_with_property(Property(lhs.symbol.create_renamed('file')))

@register_definition('open', ['file'], ['filename'])
def open_file(lhs: Expression, rhs: Expression) -> Expression:
    lval = lhs.force_get_property('file')
    if (rval := rhs.try_get_property('string')) is None:
        raise CompileError(f"open requires a string property, got {rhs}")
    if lval.is_association:
        raise CompileError(f"cannot open already opened file {lval}")
    lval.is_association = True
    lval.associated_value = open(rval.associated_value) # type: ignore
    return lhs

@register_definition('close', ['file'])
def close_file(lhs: Expression) -> Expression:
    lval = lhs.try_get_property('file')
    assert lval is not None
    if not lval.is_association:
        pwarning(f"cannot close file {lval} which is not open")
    lval.is_association = False
    lval.associated_value.close()
    return lhs

@register_definition('read', ['file'])
def read_file(lhs: Expression) -> Expression:
    lval = lhs.force_get_property('file')
    if not lval.is_association:
        raise CompileError(f"cannot read from file {lval} which is not open")
    return Expression(lhs.symbol.create_renamed('read'), [
        Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=lval.associated_value.read())
    ])


@register_definition('write', ['file'], ['string_to_write'])
def write_file(lhs: Expression, rhs: Expression) -> Expression:
    lval = lhs.force_get_property('file')
    if not lval.is_association:
        raise CompileError(f"cannot write to file {lval} which is not open")
    if (rval := rhs.try_get_property('string')) is None:
        raise CompileError(f"write requires a string property, got {rhs}")
    write_str: str = rval.associated_value # type: ignore
    lval.associated_value.write(write_str)
    return Expression(lhs.symbol.create_renamed('write'), [
        Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=write_str)
    ])