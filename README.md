**IMPORTANT**: PL is unlike other programming languages in MANY ways. 
Please make sure to read Section 1.

## 0. Introduction

PL is a programming language designed to be usable in both the preprocessing and the compiled program. 
You can think of PL as being interpreted with heavy LLVM support.

## 1. Highlights

#### Descriptive Properties

*Properties* can be added to *symbols* as trailing *tokens*. For example, `1 age` is the *symbol* `1` with *property* `age` (there is also a *default property* `integer`). This provides better specificity for operator overloading.

- numbers have default property `integer`
- strings have default property `string` 
- normal symbols have default property `identifier`

#### Operators

A function's first operand is moved before the call

\[
  \text{op}(x_1,x_2)\rightarrow x_1\text{ op }(x_2,...)
\]

More concretely, imagine the operator "concat" (`+`). We can write it as a function `+("h", "i")` but in PL it is written `"h"+"i"`, just like `1+2`.

> **Note** PL order of operations is always left to right, so we must explicitly write the mathematical expression $1+2\times3$ as `1+(2*3)` or `2*3+1`


In general, *operators* take the *lhs* and a *rhs* (default `()`) as arguments and are marked by a trailing dot (`.`/`;`/`!`) to specify that the argument should be resolved. E.g. `1+(2).` PL treats *properties* and *operators* the same. The last *property* becomes an operator whenever a dot is present. This includes cases where the *property* is implicit, like `identifier`

> Note: for convenience, we can write `1+2` because special characters combine with the next token automatically to form `1.+(2.)`. In non special-character cases though, the parenthesis (`()`) and dot (`.`/`;`/`!`) are required.

The difference between the dots are as follows:
- `.` marks that the expression up to this point should be resolved before use. This is delayed
  for expressions in compound properties until the compound property is resolved.
- `;` is an alias of `.` except it will terminate the expression.
- `!` marks that the expression up to this point should be resolved upon parse (this is useful
  for compile-time optimization).


#### Variables

In PL, **variables do not exist** but instead the operators `declare`, `assign` and `identifier` map *symbols* to values and create an illusion of variables. 

```go
x integer declare; /* the declare operator creates a map entry for `x` */
x assign(12); /* the assign operator maps 12 to `x` */
x. /* this expands into `x identifier.` which resolves into 12 */
```

> This is confusing for most people, but **variables are not implicitly resolved**. There must always be a dot following a variable if the value is desired.


#### Libraries

Python is deeply integrated into the language. Important libraries are listed below, most of them are python: 

- `lib/arithmetic.py`: to do math
- `lib/compile.py`: to compile parts of the code
- `lib/generate.py`: to vibe code (with safety)
- `lib/io.py`: to read/write files
- `lib/list.py`: to have lists
- `lib/print.py`: to have `print`
- `lib/string.py`: to have strings

Here's an example:
```go
"lib/print.py" python definition import;
"lib/string.py" python definition import;
/* `+` and `print` are defined by the imports */
"Hello, " + "World!" print;
```

#### Operator Definitions

This looks a similar to functions in other languages, except there is no explicit return value and one of the arguments comes before the function/*operator* name.

```Go
base integer power(exp integer) definition{
	half assign [ exp / 2 ];
	remainder assign [ exp.-(2 * half) ];
	result1 assign [ remainder.then[base]else[1] ];
	result2 assign [ half.then[base.power[half]]else[1] ];
	result3 assign [ result2 * result2 ];
	result1 * result3;
};
```

To prevent *resolution* before the arguments to the definition is resolved, we use `{}`. We can manually force properties to get resolved by using `!` such as in the following case:

```Go
x assign(2);
_ print2 definition{
  x!print;  /* this becomes `2 print` */
};
x assign(3);  /* x is no longer 2 */
_ print2; /* still prints 2 */
```

#### Interpretation, Generation, Compilation

It is probably most convenient to run PL in the interpreted environment, but for larger and more intensive projects, PL can manage AI code generation and code compilation.

```go
"lib/printing.py" python definition import;
"lib/generator.py" python definition import;

/* These correspond to litellm fields */
model    generate configure("provider/model"); /* e.g. "azure/gpt-4o" */
api_base generate configure("...");
api_key  generate configure("...");
api_version generate configure("...");

_ python generate(
	"cache/fib.py", 
	"implement a function 'fib' that accepts an unsigned integer 'n' and returns the n-th Fibonacci number of the sequence beginning with 1,1,2,... (0-indexed). Your solution should be implemented using DP", 
	fib
) check{
	0 fib. == 1,
	2 fib. == 2,
};
```

The above will try to generate a function that satisfies all checks, otherwise it will crash. Generated functions are cached and will remain until the prompt changes or a check fails.

```go
"lib/printing.py" python definition import;
"lib/compile.py" python definition import;

/* 0 do (...) -> returns 0 */
0 do (
	1 then(5 print)else(99 print)
) compile_to("print5.out");

0 do (
	"Hello, World!" print
) compile_to("hello.out");
```

The above behaves in a similar fashion, except with binary. Note that a slightly different resolution process than `definition` will apply here (things within parenthesis are resolved automatically here)

## 2. More Details

A program is a series of *expressions* which is composed of
one *symbol* followed by any number of *properties*.

All *symbols* and *properties* are composed of *tokens*. 
There are 5 types of tokens: 
*identifier*, *operator*, *integer*, *string*, *compound*

A *symbol* can be any of *identifier*, *operator*, *integer*, or *string*

A *property* can be any of
*identifier*, *operator*, *integer*, *string*, or *compound*

An *expression* ends upon encountering a comma (`,`) or  semicolon (`;`)

**Identifier**
Any word that contains alphabetical characters and possibly also
underscore (`_`) and digits.

Has the implicit property `identifier`

**Operator**
Any sequence of 1 or more of the following characters: `~!@#$%^&*/-+=<>|?:;.`

Has the implicit property `operator`

Must be a compound property. If there is no compound list following the operator,
the next token will be taken as the sole expression of the compound list and a `.`
will be added to the lhs and rhs. I.E. `1+x` will be `1.+(x.)`

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

- Parenthesis (`(expressions)`) will accept the expressions inside as-is
- Brackets (`[expressions]`) is an alias for `(expressions.)`
- Braces (`{expressions}`) will not resolve any `.` in expressions

Has the implicit property `compound`.

## Properties

Properties are "resolved" from right to left. Properties to the left
will not be able to see properties to the right when observing properties.
Properties do not generally need to be resolved (some are pure descriptors); 
but they are most useful when they are resolved.
*Unknown properties will raise a warning*.

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
There are no such types, all logical operators work on the `integer` type

## Lists of Properties

Here are the most important properties:
- `!`: immediately resolves the last property
- `.`: resolve the last property
- `;`: resolve the last property and begin a new expression (used as `.,`)
- `identifier declare`: creates a *variable* with the *symbol* and gives it
  the specified *properties*
- `identifier`: resolves the symbol to the *variable*'s value
- `string python definition import`: imports libraries e.g. 
  `"lib/compile.py" python definition import`

- `.(...)`: resolves the last property with the specified arguments
- `identifier assign(...)`: copies the *properties* of the expression in 
  parenthesis to the *variable*
- `do(...)`: this is a no-op. Use this for evaluating *expressions* with side effects
- `definition(...)`: creates a user-defined property (see next section)
- `integer then(...)`: resolves into the enclosed value if the lhs is non-0 otherwise 
  resolves to 0
- `integer else(...)`: resolves into the enclosed value if the lhs is 0 otherwise
  resolves to lhs.
- `integer then(...) else(...)`: resolves into the enclosed value of `then` if lhs is 
  non-0 otherwise resolves into the enclosed value of `else`


Here's a list of the remaining built-in properties:
- `operator`:
- `integer`: 
- `string`: a primative type. Not indexable nor iterable
- `properties`: gives a list of the *properties*
  of all properties of an `expression` in right-to-left order.
- `assert(...)`: throws an error if the property inside is not non-0

### Libraries

#### `lib/arithmetic.py`

- `integer +(...)`
- `integer -(...)`
- `integer *(...)`
- `integer /(...)`
- `integer ==(...)`
- `integer !=(...)`
- `integer <(...)`
- `integer <=(...)`
- `integer >(...)`
- `integer >=(...)`

#### `lib/compile.py`

- `compile`: not to be called directly; requires variables `__BUILDER__`, `__MODULE__`, and `__IMPORT_PATH__` to be defined; generates LLVM IR
- `compile_to(filename)`: performs compilation of the left hand side and outputs the file. `filename` must end in `.o` or `.out`

#### `lib/generate.py`
- `generate configure(value)`: configures a field of `litellm` to be used for generate
- `string python generate(prompt, definitions...)`: generates the file specified in the lhs and imports the specified definitions
- `string generate(...) check(...)`: performs generation until the check passes

#### `lib/io.py`
- `file`
- `file open`
- `file close`
- `file read`: reads the contents of the entire file

#### `lib/list.py`

- `list`
- `list append(value)`
- `list at(index)`
- `list each(definition)`: maps each element of the lhs into a new value 
  via definition

#### `lib/pointer.py`
- `pointer`
- `pointer dereference`
- `identifier reference`

#### `lib/print.py`
- `print`

#### `lib/string.py`
- `string`