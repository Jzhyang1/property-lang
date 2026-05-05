if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, unary_apply, binary_apply, multi_apply, pwarning, CompileError


# We extend compilation
import llvmlite.ir as ir
if 'definitions' in globals():
    compile = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'compile.py')
    cstdlib = globals()['definitions'].ImportPythonDefinition.import_module(__file__, 'compile/cstdlib.py')
else:
    raise ImportError("definitions module not found, cannot import compile module")


@builtin_definition
class StringEqualDefinition(Definition):
    symbol = '=='
    param_names = ['rhs']
    property_names = ['string']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.force_get_property('string')
        rval = rhs.force_get_property('string')
        res = lval.associated_value == rval.associated_value
        return Expression(lhs.symbol.create_renamed('=='), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
        ])

@builtin_definition
class StringNotEqualDefinition(Definition):
    symbol = '!='
    param_names = ['rhs']
    property_names = ['string']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.force_get_property('string')
        rval = rhs.force_get_property('string')
        res = lval.associated_value != rval.associated_value
        return Expression(lhs.symbol.create_renamed('!='), [
            Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
        ])

@builtin_definition
class StringConcatDefinition(Definition):
    symbol = '+'
    property_names = ['string']
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        lval = lhs.force_get_property('string')
        rval = rhs.force_get_property('string')
        return Expression(lhs.symbol.create_renamed('+'), [
            Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=lval.associated_value + rval.associated_value)
        ])
    
@builtin_definition
class StringSplitDefinition(Definition):
    symbol = 'split'
    property_names = ['string']
    param_names = ['delimiters...'] # not included in the result
    @multi_apply
    def apply(self, lhs: Expression, rhs: list[Expression], scope: Scope) -> Expression:
        lval = lhs.force_get_property('string')
        delimiters = []
        for r in rhs:
            delimiters.append(r.force_get_property('string').associated_value)
        res = [lval.associated_value]
        for d in delimiters:
            new_res = []
            for s in res:
                new_res.extend(s.split(d))
            res = new_res
        return Expression(lhs.symbol.create_renamed('split'), [
            Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=res)
        ])
    

# Compilation

compile.add_initializer(cstdlib.define_strcmp)
compile.add_initializer(cstdlib.define_strcpy)
compile.add_initializer(cstdlib.define_strcat)
compile.add_initializer(cstdlib.define_strlen)
compile.add_initializer(cstdlib.define_malloc)

@builtin_definition
class CompileStringEqualDefinition(Definition):
    symbol = 'compile'
    property_names = ['string', '==']
    param_names = ['rhs']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, rprop = lhs.discard_properties_after('==')
        if len(rprop.compound_properties) != 1:
            raise CompileError("expected exactly one property after '==' for string comparison", anchor=rprop.property)
        rhs = rprop.compound_properties[0]

        builder = compile.get_compile_construct(scope, '__BUILDER__')
        module = compile.get_compile_construct(scope, '__MODULE__')

        lval = builder.inttoptr(compile.get_compiled(lhs, scope), ir.PointerType(ir.IntType(8)))
        rval = builder.inttoptr(compile.get_compiled(rhs, scope), ir.PointerType(ir.IntType(8)))
        # We can use the C strcmp function to compare the strings
        res = builder.call(module.get_global('strcmp'), [lval, rval])
        # extend to 64-bit
        res = builder.zext(res, ir.IntType(64))
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res)
        int_property = Property(lhs.symbol.create_renamed('integer'))
        return lhs.create_with_property(int_property).replace_property('compile', compile_prop)
        
@builtin_definition
class CompileStringConcatDefinition(Definition):
    symbol = 'compile'
    property_names = ['string', '+']
    param_names = ['rhs']
    @unary_apply
    def apply(self, lhs: Expression, scope: Scope) -> Expression:
        lhs, rprop = lhs.discard_properties_after('+')
        if len(rprop.compound_properties) != 1:
            raise CompileError("expected exactly one property after '+' for string concatenation", anchor=rprop.property)
        rhs = rprop.compound_properties[0]

        builder = compile.get_compile_construct(scope, '__BUILDER__')
        module = compile.get_compile_construct(scope, '__MODULE__')

        print('l', lhs, 'r', rhs)

        lval = builder.inttoptr(compile.get_compiled(lhs, scope), ir.PointerType(ir.IntType(8)))
        rval = builder.inttoptr(compile.get_compiled(rhs, scope), ir.PointerType(ir.IntType(8)))

        # We can use the C strcat function to concatenate the strings
        # However, we need to allocate enough space for the result first
        lval_len = builder.call(module.get_global('strlen'), [lval])
        rval_len = builder.call(module.get_global('strlen'), [rval])
        total_len = builder.add(lval_len, rval_len)
        total_len_with_null = builder.add(total_len, ir.Constant(ir.IntType(64), 1))
        malloced_ptr = builder.call(module.get_global('malloc'), [total_len_with_null])
        lcopied = builder.call(module.get_global('strcpy'), [malloced_ptr, lval])
        res = builder.call(module.get_global('strcat'), [lcopied, rval])
        res = builder.ptrtoint(malloced_ptr, ir.IntType(64))
        compile_prop = Property(lhs.symbol.create_renamed('compile'), is_association=True, associated_value=res)
        return lhs.replace_property('compile', compile_prop)