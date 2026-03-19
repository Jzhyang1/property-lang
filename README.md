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
- Brackets (`[...]`) will accept the expressions inside as-is
- Braces (`{...}`) will treat all expressions inside as right-to-left resolution 
  (this is used primarily for resolution definitions; rule of thumb is that
  there should be only 1 expression inside braces)

Has the implicit property `compound`.

## More about Properties

Properties are "resolved" from right to left. Properties to the left
will not be able to see properties to the right when observing properties.
Properties do not generally need to be resolved (some are pure descriptors); 
but they are most useful when they are resolved.
*Unknown properties will raise a warning*.

We mentioned the property removal. Here are the most important properties:
- `.`: resolves the last property
- `;`: resolve the last property (used as `.,`)
- `declare`: `identifier`: resolves by defining a variable with the symbol; need to 
  resolve future occurances of the symbol to use the variable.
- `list`: does not resolve, but lets the language know that the expression
  is a list of expressions
- `identifier`: resolves the symbol to a variable
- `import`: expects a string property; additional language specifier can be included 
  otherwise defaults to pl script import. Example `"compile.py" python import`
- `structure`: does not resolve, but lets the language know that the 
  expression has fields

- `.(...)`:* resolves the last property with the specified arguments
- `assign(...)`: `identifier`: assigns to the variable associated with a symbol
- `do(...)`: this is a no-op. Use this for evaluating arguments
- `field_set(...)`: `structure`: sets the properties of the field given by the argument 
  symbol to their properties
- `field_get(...)`: `structure`: takes the symbol given and gets its associated value
- `index(...)`: `list`: resolves into the idx index element (0-based) of a list
- `resolution(...)`: resolves the symbol and preceding properties to a 
  user-defined resolution sequence (see next section)
- `then(...)`: resolves into the enclosed value if there is a non-0 integer property
  otherwise a no-op
- `else(...)`: resolves into the enclosed value if there is a 0 integer property
  otherwise searches for the last `then` property to resolve, no-op if not found


Here's a list of all remaining built-in properties:
- `expression`:*
- `symbol`:* this property cannot be added to an expression
- `property`: this property cannot be added to an expression
- `operator`:
- `integer`: 
- `string`: a primative type. Not indexable nor iterable
- `compound`:* shorthand for `indexable[expression] iterable[expression]`
- `symbols`:* gives the `symbol` of an `expression`
- `properties`: gives an `indexable[property] iterable[property]` 
  of all properties of an `expression` in right-to-left order.
- `invoke(...)`:* gives the expression containing properties up to 
  and including the last occurrence of the specified property
- `each(item_placeholder, ...)`: applies the body to each item
  where `item_placeholder` is the symbol used in the body for the 
  iterated item, and the result is the 1-to-1 mapping of each item 
  to the result of the body
- `assert(...)`: throws an error if the property inside is not non-0

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