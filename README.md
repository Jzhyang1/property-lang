**IMPORTANT**: PL is unlike other programming languages in MANY ways. 
Please read through section 1, "Highlights" to make sure you don't end
up stuck in sill rabbit holes.

## 0. Introduction

PL is a programming language. We allow full control over the program
behavior during both the compilation phase and the compiled program. 
At the same time, we provide built-in libraries to make programming easy.
By default, PL is interpreted, but there are caveats to that.

## 1. Highlights

#### Operators

A function's first operand is moved before the call

\[
  \text{op}(x_1,x_2)\rightarrow x_1\text{ op }(x_2,...)
\]

More concretely, `concat("h", "i")` is written `"h" concat("i")` and `1+2` is written `1 +(2)`.

> **Note** we don't have order of operations, instead we must explicitly write things like `1+2*3` as `1+(2*(3).)` (we will get into the `.` next) or `2*(3).+(1)`


#### Descriptive Properties

We define additional "properties" by having additional *tokens* after the main *token*. For example, `1 age` describes `1` and `"a.py" python definition` describes `"a.py"`. This is better specificity for operator overloading.

The *default property* `integer` is given to numbers, `string` is given to strings, `identifier` is given to normal words.

Almost every file will have the following line, which says that there is some `"lib/printing.py"` that is a `python definition`, on which we will perform `import`
```
"lib/printing.py" python definition import;
```

There is no need to specify who is an operator among all the properties, only those properties that are *resolved* will be interpreted as an operator. A property is *resolved* when it is followed by a `.` or `;` (combined `.,`). Back to `2 *(3). +(1)`, we need to apply `2 *(3)` first (we omitted the `;`).

#### Variables

This is confusing for most people, but **variables are not implicitly resolved**. For instance, the following code will give `y` the value `x identifier` rather than `1`.

```
x assign(1);
y assign(x);  /* use y assign(x.); instead */
```

#### Operator Definitions

```
base integer power(exp integer) definition{
	half assign(exp./(2).),
	remainder assign(exp.-(half).-(half).),
	result1 assign(remainder.then(base.)else(1).),
	result2 assign(base.power(half.).),
	result1 *(result2.)
};
```

We almost never use curly braces (`{}`) except for select lines within operator definitions. They force lines inside to be *resolved* together. We also use commas here instead of semicolons to prevent us from triggering *resolution*.

#### Interpretation, Generation, Compilation

It is probably most convenient to run PL in the interpreted environment, but for larger and more intensive projects, PL can manage AI code generation and code compilation.

```
"lib/printing.py" python definition import;
"lib/generator.py" python definition import;

/* These correspond to litellm fields */
model    generate configure("provider/model"); /* e.g. "azure/gpt-4o"
api_base generate configure("...");
api_key  generate configure("...");
api_version generate configure("...");

_ python generate(
	"cache/fib.py", 
	"implement a function 'fib' that accepts an unsigned integer 'n' and returns the n-th Fibonacci number of the sequence beginning with 1,1,2,... (0-indexed). Your solution should be implemented using DP", 
	fib
) check{
	0 fib. ==(1),
	2 fib. ==(2),
};
```

The above will try to generate a function that satisfies all checks, otherwise it will crash. Generated functions are cached and will remain until the prompt changes or a check fails.

```
"lib/printing.py" python definition import;
"lib/compile.py" python definition import;

code do(12 print.) compile("print12.out");
code do(1 then(5 print.)else(99 print.).) compile("print5.out");
```

The above behaves in a similar fashion, except with binary. Note that the `do(...)` is not resolved.

## 2. More Details

We abstract a program as a series of 
"symbols" with "properties" that are resolved by either the
interpreter/compiler or user-defined definitions.

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
- Braces (`{...}`) will treat all expressions inside as right-to-left definition 
  (this is used primarily for definition definitions; rule of thumb is that
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
- `definition(...)`: resolves the symbol and preceding properties to a 
  user-defined definition sequence (see next section)
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
 *   define all properties required on expr to apply this definition
 * new_property
 *   the property name that will trigger the definition
 * body
 *   resolves to an expression to replace the entire prior sequence
 */
symb required_properties new_property definition{
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
symb required_properties new_property(param1 param1_properties, param2 param2_properties) definition{
    body
}
```

## Types

### Booleans
There are no such types, all logical operators work on the int type