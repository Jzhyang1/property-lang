import os
from typing import Any
if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, binary_apply, pwarning, perror, import_raw_python_file, expression_to_associated_value


class GeneratorError(Exception):
    pass

configuration: dict[str, Any] = {
    'model': 'gpt-4'
}

def generate_file(output_file: str, prompt: str) -> None:
    from litellm import completion, ModelResponse
    if 'messages' in configuration or 'stream' in configuration:
        perror("can not have 'messages' or 'stream' in configuration")

    resp = completion(
        messages=[
            {"role": "system", "content": "respond in Python code only, no markdown formatting"},
            {"role": "user", "content": prompt}
        ],
        stream=False,
        **configuration
    )
    assert isinstance(resp, ModelResponse)
    content = resp.choices[0].message.content
    if content is None:
        raise GeneratorError("Generator did not return any content")
    with open(output_file, 'w') as f:
        f.write(content)


@builtin_definition
class GenerateDefinition(Definition):
    symbol = 'generate'
    property_names = ['python']
    param_names = ['output_file', 'prompt', 'definitions...']
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        output_file, prompt, *definitions = args
        output_file, prompt = output_file.try_get_property('string'), prompt.try_get_property('string')
        if output_file is None or prompt is None:
            perror(f'Generator requires strings (output_file, prompt), got ({output_file}, {prompt})')
            return lhs
        output_file, prompt = output_file.associated_value, prompt.associated_value

        imports = [defn.symbol.s for defn in definitions]
        if os.path.exists(output_file) and os.path.exists(f'cache/generator/{output_file}.log'):
            # We cached the previous prompt in the file so that we can decide when to use
            # a cached version of the generator output, and when to call the generator again.
            with open(f'cache/generator/{output_file}.log', 'r') as f:
                previous = f.read()
            if previous == prompt:
                import_raw_python_file(lhs.symbol.file, output_file, imports, scope)
            
        # We need to generate the output source from scratch
        generate_file(output_file, prompt)
        os.makedirs('cache/generator', exist_ok=True)
        with open(f'cache/generator/{output_file}.log', 'w') as f:
            f.write(prompt)
        # then we create load the generated source and add definitions to `scope`
        import_raw_python_file(lhs.symbol.file, output_file, imports, scope)
        return lhs
    
@builtin_definition
class CheckDefinition(Definition):
    symbol = 'check'
    property_names = ['generate']
    param_names = ['conditions...'] # we check through all of the conditions, and if any of them fail, we regenerate the source for the associated generator
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        generate = lhs.try_get_property('generate')
        assert generate is not None
        # Get to the associated generator definition
        properties = []
        for p in lhs.properties:
            properties.append(p)
            if p == generate: break
        new_lhs = Expression(lhs.symbol, properties)
        from main import resolve_last_property
        # repeat until all checks pass
        for _ in range(10): # max 10 iterations to prevent infinite loops
            resolved = resolve_last_property(new_lhs, scope)
    
            for condition in args:
                condition_evaluated = resolve_last_property(condition, scope)
                if (val := condition_evaluated.try_get_property('integer')) is None:
                    pwarning(f'Condition {condition} did not evaluate to an integer, got {condition_evaluated}')
                elif val.associated_value == 0:
                    break
            else:
                # all conditions passed, we are done
                return resolved
            
        perror(f'Conditions {args} exceeded retries, giving up')

@builtin_definition
class ConfigureDefinition(Definition):
    symbol = 'configure'
    property_names = ['generate']
    param_names = ['value'] # of the form `property generate configure(value)`
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        configuration[lhs.symbol.s] = expression_to_associated_value(rhs)
        return rhs