if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, binary_apply, pwarning, CompileError


@builtin_definition
class FileOpenDefinition(Definition):
    symbol = 'open'
    property_names = ['file']
    param_names = ['filename']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.try_get_property('file')
        assert lval is not None
        if (rval := rhs.try_get_property('string')) is None:
            raise CompileError(f"open requires a string property, got {rhs}")
        
        if lval.is_association:
            raise CompileError(f"cannot open already opened file {lval}")

        lval.is_association = True
        lval.associated_value = open(rval.associated_value) # type: ignore
        return lhs

@builtin_definition
class FileCloseDefinition(Definition):
    symbol = 'close'
    property_names = ['file']
    def apply(self, lhs: Expression, rhs: list[Expression], scope: Scope) -> Expression:
        lval = lhs.try_get_property('file')
        assert lval is not None
        if not lval.is_association:
            pwarning(f"cannot close file {lval} which is not open")
        lval.is_association = False
        lval.associated_value.close()
        return lhs

@builtin_definition
class FileReadDefinition(Definition):
    symbol = 'read'
    property_names = ['file']
    def apply(self, lhs: Expression, rhs: list[Expression], scope: Scope) -> Expression:
        lval = lhs.try_get_property('file')
        assert lval is not None
        if not lval.is_association:
            raise CompileError(f"cannot read from file {lval} which is not open")
        return Expression(lhs.symbol.create_renamed('read'), [
            Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=lval.associated_value.read())
        ])
    
@builtin_definition
class FileReadToDefinition(Definition):
    symbol = 'read'
    property_names = ['file']
    param_names = ['read_to_string']    # read_to_string is included in the result
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.try_get_property('file')
        assert lval is not None
        if not lval.is_association:
            raise CompileError(f"cannot read from file {lval} which is not open")
        if (rval := rhs.try_get_property('string')) is None:
            raise CompileError(f"read requires a string property, got {rhs}")
        end_str: str = rval.associated_value # type: ignore
        # read the file until rval.associated_value is found, and return the read string
        read_str = ''
        while True:
            char = lval.associated_value.read(1)
            if char == '':
                break
            read_str += char
            if read_str.endswith(end_str):
                break
        return Expression(lhs.symbol.create_renamed('read'), [
            Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=read_str)
        ])