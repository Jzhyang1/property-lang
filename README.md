PL is a programming language. We try to allow full control over
the program both in the compiled program as well as during the
compilation process. We abstract a program as a series of 
"symbols" with "properties" that are resolved by either the
interpreter/compiler or user-defined resolutions.

- The 5 types of tokens: identifier, operator, integer, string, and compound
- Symbol: the first token of a series of tokens
- Property: any additional tokens that follow a symbol, or a property removal
  given by a forward slash followed by the property to remove (`\token`)
- Expression: refers to both symbols and properties

**Identifier**
Any word that contains alphabetical characters and possibly also
underscore (`_`) and digits.

Has the implicit property `identifier`

**Operator**
Any sequence of 1 or more of the following characters: `~!@#$%^&*/-+=<>|?:;.`

Has the implicit property `operator`

**Integer**
Any integer number

Has the implicit property `integer`

**String**
Any sequence of characters enclosed in double quotes (`"..."`)

Has the implicit property `string`

**Compound**
A token followed by a comma-separated series of token sequences 
enclosed in one of the following:
parenthesis (`(...)`), brackets (`[...]`), or braces (`{...}`)

- Parenthesis (`(...)`) will accept the expressions inside as-is
- Brackets (`[...]`) will resolve all variables within
- Braces (`{...}`) will resolve all variables within and resolve the last property of each expression

Has the implicit property `compound`.

## More about Properties

Properties are "resolved" from right to left. Properties to the left
will not be able to see properties to the right when observing properties.
Properties do not generally need to be resolved (some are pure descriptors); 
but they are most useful when they are resolved.
*Unknown properties will raise a warning*.

We mentioned the property removal. Several other special properties exist:
- `expression`:*
- `symbol`:* this property cannot be added to an expression
- `property`: this property cannot be added to an expression
- `identifier`: resolves the symbol to a variable
- `operator`:
- `integer(...)`: 
- `string(...)`: a primative type. Not indexable nor iterable
- `compound`:* shorthand for `indexable[expression] iterable[expression]`
- `symbols`:* gives the `symbol` of an `expression`
- `properties`: gives an `indexable[property] iterable[property]` 
  of all properties of an `expression` in right-to-left order.
- `resolution(...)`: resolves the symbol and preceding properties to a 
  user-defined resolution sequence (see next section)
- `invoke(...)`:* gives the expression containing properties up to 
  and including the last occurrence of the specified property
- `declare`
- `assign(...)`: assigns to a symbol
- `do(...)`: this is a no-op. Use this for evaluating arguments
- `indexable`: 
- `iterable`: 
- `index[/*idx int*/]`: gets the idx index element (0-based) of an indexable
- `each(item_placeholder, ...)`: applies the body to each item
  where `item_placeholder` is the symbol used in the body for the 
  iterated item, and the result is the 1-to-1 mapping of each item 
  to the result of the body
- `import`: expects a string property; additional language specifier can be included otherwise defaults to pl script import. Example `"compile.py" python import`
- `assert(...)`: throws an error if the property inside is not non-0
- `.`: resolves the last property
- `.(...)`:* resolves the last property with the specified arguments
- `;`: resolve the last property (used as `.,`)

## Declaring Variables
```Kotlin
var_name properties declare
```

## Defining Properties

A property is defined as follows:
```Kotlin
/* symb (or whatever name is used) 
 *   can be used inside the body as an expression instance 
 * required_properties
 *   define all properties required on expr to apply this resolution
 * new_property
 *   the property name that will trigger the resolution
 * body
 *   resolves to an expression to replace the entire prior sequence
 */
symb required_properties new_property resolution{
    body
}
```

For unresolved properties, `body` is usually safety checks
on `placeholder` and `placeholder` itself is returned.


Parameters can be defined as follows:
```Kotlin
/* param1, param2 (or whatever name is used) 
 *   can be used inside the body as expression instances 
 *   with the specified properties matched.
 *   their properties will usually be types like integer/string/etc
 */
symb required_properties new_property(param1 param1_properties, param2 param2_properties) resolution{
    body
}
```

## Types

### Booleans
There are no such types, all logical operators work on the int type