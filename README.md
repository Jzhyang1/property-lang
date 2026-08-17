## 0. Introduction

3 main ideas:

1. interpreted but generates artifacts (like Makefiles)
2. Parallel interpretation and 1-pass
3. Type checking

## 1. Highlights

#### Expressions

Every expression is a stack of *properties*. The stack is *resolved* back-to-front by pattern-matching. *Resolution* must be explicit. 

In the example below, the properties are `generate`, `import` and `check`. The properties have *args* attached to them via parenthesis (`()`), brackets (`[]`) or braces (`{}`). 

We match the longest pattern that looks like `check`, `import check`, or `generate import check`.

```go
generate("create a var x=1") import(x) check({x == 1;}).
```

The dot (`.`) *resolves* what the *expression* has stacked up so far. The semicolon (`;`) is the same but also clears the stack.

#### Parenthesis

- Parenthesis (`()`) doesn't *resolve* its contents by default, but allows things inside to *resolve*.
- Brackets (`[]`) *resolve* its contents by default. This is primarily used for arithmetic.
- Braces (`{}`) takes everything inside as-is. It does not *resolve* at all.

Any of these parenthesis can be used in conjunction with a *property* to be passed as its *args*. There must not be a space between the *property* and the parenthesis to be passed as *args*.

#### Chained Expressions

Expressions continue to build until a comma (`,`) or semicolon (`;`) is reached. E.g. `fib(3).pow(2).mod(17);`. 
- `fib` will get `(undefined,3)`
- `pow` will get `(6,2)`
- `mod` will get `(36,17)`

> **Note** PL order of operations is always left to right, so we must explicitly write the mathematical expression $1+2\times3$ as `1+[2*3]` or `2*3+1`

> **Note** for convenience, we can write `1+2` because *special characters* combine with the next property via the pattern `1.+(2.)` if it does not already have a parameter.

#### Defining Resolutions

To define a property resolution, we do something like this:

```go
foo(arg2) prefix(arg1) def{
  arg1 + arg2;
};
/* call via `1 foo(2)` */
```

> **Note** the braces (`{}`) are used to delay resolution (so we don't try to find the result of `arg1 + arg2` before the function is called). 

Symbolic variables are defined in the same way.

```go
pi def[22 / 7]; /* This is not how pi is actually defined */
```

> A source of confusion for some: **variables are not implicitly resolved**. The variable must be followed by a dot, operator, or enclosed in brackets (`[]`) if the value is desired.

#### Mutables

Use mutable definitions for compound structures.

```go
/* defines coords, coords x, coords y, coords x def, coords y def */
coords struct{
  x, y
};

/* a copy of the expression `coords` is created by coords. */
point def[coords[0, 0]];

/* coords x def perform operations on the x of the copy of coords */
point.x def[0];
point.y def[1];
```

#### Parallel Expressions

We have already encountered parallelism without pointing it out. Take the following example again. Properties `a`,`b`,`c` will all resolve in parallel. If any of those properties encounter something it is *unable to do*, it will block. If anthing remains blocked when all other parallel-executing properties terminate, we crash.

```go
generate(a.) import(b.) check(c.).
```

For example, we may have something like this.

```go
/* a */
x def[1]; /* first definition of x */
/* b */
y def[x]; /* y will block until x is defined */
```

A few other parallelism examples:

```go
active def[intensity > 0]
```

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

This looks a similar to functions in other languages, the differences are:
- the first argument comes before the function/*operator* name
- parameter types (optional) comes in an `is` property
- the return type (optional) comes after the body
- the return value is the last expression in the definition

```Go
base is(integer) power(exp is(integer)) definition{
	half assign [ exp / 2 ];
	remainder assign [ exp.-(2 * half) ];
	result1 assign [ remainder.then[base]else[1] ];
	result2 assign [ half.then[base.power[half]]else[1] ];
	result3 assign [ result2 * result2 ];
	result1 * result3;
} return(.integer);
```

To prevent *resolution* before the arguments to the definition is resolved, we use `{}`. We can manually force properties to get resolved by using `!` such as in the following case:

```Go
x assign(2);
.print2 definition{
  x!print;  /* this becomes `2 print` */
};
x assign(3);  /* x is no longer 2 */
.print2; /* still prints 2 */
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

"cache/fib.py" python generate( 
	"implement a function 'fib' that accepts an unsigned integer 'n' and returns the n-th Fibonacci number of the sequence beginning with 1,1,2,... (0-indexed). Your solution should be implemented using DP", 
) import(fib) check{
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

Tokenization

```ebnf
(* Whitespace *)
SPACE         ::= [ \t\n]+

(* Identifiers & Keywords *)
TOKEN         ::= [_0-9a-zA-Z]+

(* String Literals *)
STR           ::= '"' ( '\\"' | [^"] )* '"'

(* Matched Brackets *)
OPAREN_ROUND  ::= "("
CPAREN_ROUND  ::= ")"
OPAREN_SQUARE ::= "["
CPAREN_SQUARE ::= "]"
OPAREN_CURLY  ::= "{"
CPAREN_CURLY  ::= "}"

(* Delimiters & Operators *)
SEP           ::= "," | ";"
RES           ::= "."
OP            ::= [^ \t\n_0-9a-zA-Z"()\[\]{};,.]+
```

Syntax
```ebnf
(* Matched Parentheses *)
PAREN_ROUND   ::= OPAREN_ROUND SPACE? TUPLE SPACE? CPAREN_ROUND
PAREN_SQUARE  ::= OPAREN_SQUARE SPACE? TUPLE SPACE? CPAREN_SQUARE
PAREN_CURLY   ::= OPAREN_CURLY SPACE? TUPLE SPACE? CPAREN_CURLY

PARENTHESIZED ::= PAREN_ROUND | PAREN_SQUARE | PAREN_CURLY

(* Safe means adjacent whitespace isn't problematic *)
SAFE_PROP     ::= STR
                | TOKEN
                | OP
                | TOKEN PARENTHESIZED
                | OP PARENTHESIZED

DANGEROUS_PROP::= PARENTHESIZED

PROP          ::= SAFE_PROP | DANGEROUS_PROP

(* Primary Term: Handles adjacent properties / space sensitivity *)
EXPR  ::= PROP ( ( SPACE? SAFE_PROP ) | ( SPACE DANGEROUS_PROP ) )*

(* Tuples & Separated Lists *)
EMPTY_TUPLE   ::= ""
NONEMPTY_TUPLE::= EXPR ( SPACE? SEP SPACE? EXPR )*
TUPLE         ::= NONEMPTY_TUPLE | EMPTY_TUPLE
```

A program is a series of *expressions* which is composed of
one *symbol* followed by any number of *properties*.

All *symbols* and *properties* are composed of *tokens*. 
There are 5 types of tokens: 
*identifier*, *operator*, *integer*, *string*, *compound*

A *symbol* can be any of *identifier*, *operator*, *integer*, or *string*

A *property* can be any of
*identifier*, *operator*, *integer*, *string*, or *compound*

An *expression* ends upon encountering a comma (`,`) or  semicolon (`;`)

**Resolution**
The dot (`.`) is a property-less placeholder when used as a symbol.
It is common to see `.function;` for functions that don't take arguments.

See Section **Properties** for how it is used to resolve properties.

**Identifier**
Any word that contains alphabetical characters and possibly also
underscore (`_`) and digits.

Has the implicit property `identifier`

**Operator**
Any sequence of 1 or more of the following characters: `~!@#$%^&*/-+=<>|?:`

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
- `.(...)`: resolves the last property with the specified arguments
- `;`: resolve the last property and begin a new expression (used as `.,`)
- `identifier`: resolves the symbol to the *variable*'s value
- `identifier assign(...)`: copies the *properties* of the expression in 
  parenthesis to the *variable*
- `identifier declare`: creates a *variable* with the *symbol* and gives it
  the specified *properties*
- `string import`: imports another `.lang` file
- `string python definition import`: imports libraries e.g. 
  `"lib/compile.py" python definition import`
- `context`: applies the properties of the lhs to all expressions in scope
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
- `file write`: write the contents specified to the file

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
- `string split`