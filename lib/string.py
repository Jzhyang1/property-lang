from constants import Definition, Scope, Expression, Property, Token
from definitions import register_definition
import definitions

# We extend compilation
import llvmlite.ir as ir
compile = definitions.import_module(__file__, 'compile.py')


@register_definition('==', ['string'], ['operand'])
def equal(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    lval = lhs.force_get_property('string')
    rval = rhs.force_get_property('string')
    res = lval.associated_value == rval.associated_value
    return Expression(lhs.symbol.create_renamed('=='), [
        Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
    ])

@register_definition('!=', ['string'], ['operand'])
def not_equal(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    lval = lhs.force_get_property('string')
    rval = rhs.force_get_property('string')
    res = lval.associated_value != rval.associated_value
    return Expression(lhs.symbol.create_renamed('!='), [
        Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=res)
    ])

@register_definition('+', ['string'], ['operand'])
def concat(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    lval = lhs.force_get_property('string')
    rval = rhs.force_get_property('string')
    return Expression(lhs.symbol.create_renamed('+'), [
        Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=lval.associated_value + rval.associated_value)
    ])

@register_definition('length', ['string'], [])
def length(lhs: Expression, scope: Scope) -> Expression:
    sval = lhs.force_get_property('string')
    return Expression(lhs.symbol.create_renamed('length'), [
        Property(lhs.symbol.create_renamed('integer'), is_association=True, associated_value=len(sval.associated_value))
    ])

@register_definition('split', ['string'], ['delimiters...'])
def split(lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
    lval = lhs.force_get_property('string')
    delimiters = []
    for r in args:
        delimiters.append(r.force_get_property('string').associated_value)
    res_strings: list[str] = [lval.associated_value]
    for d in delimiters:
        new_res = []
        for s in res_strings:
            new_res.extend(s.split(d))
        res_strings = new_res
    res: list[Expression] = [
        Expression(lhs.symbol.create_renamed('split_result'), [
            Property(lhs.symbol.create_renamed('string'), is_association=True, associated_value=s)
        ]) for s in res_strings
    ]
    return Expression(lhs.symbol.create_renamed('split'), [
        Property(lhs.symbol.create_renamed('list'), is_association=True, associated_value=res)
    ])

# Compilation

@register_definition('==', ['compile', 'string'], ['operand'])
def compile_strequal(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')

    lval = compile.get_compiled(lhs, scope)
    rval = compile.get_compiled(rhs, scope)
    # We can use the C strcmp function to compare the strings
    res = builder.call(module.get_global('strcmp'), [lval, rval])
    # extend to 64-bit
    res = builder.zext(res, ir.IntType(64))
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
    int_property = Property(lhs.symbol.create_renamed('integer'))
    return lhs.create_with_property(int_property).replace_property('compiled_result', compiled_prop)

@register_definition('+', ['compile', 'string'], ['operand'])
def compile_concat(lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')

    lval = compile.get_compiled(lhs, scope)
    rval = compile.get_compiled(rhs, scope)
    # We can use the C strcat function to concatenate the strings
    # However, we need to allocate enough space for the result first
    strlen = module.get_global('strlen')
    lval_len = builder.call(strlen, [lval])
    rval_len = builder.call(strlen, [rval])
    total_len = builder.add(lval_len, rval_len)
    total_len_with_null = builder.add(total_len, ir.Constant(ir.IntType(64), 1))
    malloced_ptr = builder.call(module.get_global('malloc'), [total_len_with_null])
    lcopied = builder.call(module.get_global('strcpy'), [malloced_ptr, lval])
    res = builder.call(module.get_global('strcat'), [lcopied, rval])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
    return lhs.replace_property('compiled_result', compiled_prop)

@register_definition('length', ['compile', 'string'])
def compile_length(lhs: Expression, scope: Scope) -> Expression:
    builder = compile.get_compile_construct(scope, '__BUILDER__')
    module = compile.get_compile_construct(scope, '__MODULE__')

    lval = compile.get_compiled(lhs, scope)
    res = builder.call(module.get_global('strlen'), [lval])
    compiled_prop = Property(lhs.symbol.create_renamed('compiled_result'), is_association=True, associated_value=res)
    int_property = Property(lhs.symbol.create_renamed('integer'))
    return lhs.create_with_property(int_property).replace_property('compiled_result', compiled_prop)