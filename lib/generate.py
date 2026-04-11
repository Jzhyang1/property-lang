import os
from typing import Any
if not '__LANG__' in globals():
    from constants import Definition, Scope, Expression, Property, Token
    from definitions import builtin_definition, binary_apply, multi_apply, pwarning, CompileError, import_raw_python_file, expression_to_associated_value


class GeneratorError(Exception):
    pass

configuration: dict[str, Any] = {
    'model': 'gpt-4'
}

def generate_file(output_file: str, prompt: str) -> None:
    from litellm import completion, ModelResponse
    if 'messages' in configuration or 'stream' in configuration:
        raise CompileError("can not have 'messages' or 'stream' in configuration")

    resp = completion(
        messages=[
            {"role": "system", "content": "respond in Python code only, no tests and no markdown formatting"},
            {"role": "user", "content": prompt}
        ],
        stream=False,
        **configuration
    )
    assert isinstance(resp, ModelResponse)
    content = resp.choices[0].message.content
    if content is None:
        raise GeneratorError("Generator did not return any content")
    
    # There is still a chance that the model returned content in markdown
    content = content.lstrip('```python').rstrip('```')
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        f.write(content)


@builtin_definition
class GenerateDefinition(Definition):
    symbol = 'generate'
    property_names = ['python']
    param_names = ['output_file', 'prompt', 'definitions...']
    @multi_apply
    def apply(self, lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
        output_file, prompt, *definitions = args
        output_file, prompt = output_file.try_get_property('string'), prompt.try_get_property('string')
        if output_file is None or prompt is None:
            raise CompileError(f'Generator requires strings (output_file, prompt), got ({output_file}, {prompt})')
            return lhs
        output_file, prompt = output_file.associated_value, prompt.associated_value
        cache_file = f'cache/generator/{output_file}.log'

        imports = [defn.symbol.s for defn in definitions]
        if os.path.exists(output_file) and os.path.exists(cache_file):
            # We cached the previous prompt in the file so that we can decide when to use
            # a cached version of the generator output, and when to call the generator again.
            with open(cache_file, 'r') as f:
                previous = f.read()
            if previous == prompt:
                import_raw_python_file(lhs.symbol.file, output_file, imports, scope)
                return lhs
            
        # We need to generate the output source from scratch
        generate_file(output_file, prompt)
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, 'w') as f:
            f.write(prompt)
        # then we create load the generated source and add definitions to `scope`
        import_raw_python_file(lhs.symbol.file, output_file, imports, scope)
        return lhs
    
@builtin_definition
class CheckDefinition(Definition):
    symbol = 'check'
    property_names = ['generate']
    param_names = ['conditions...'] # we check through all of the conditions, and if any of them fail, we regenerate the source for the associated generator
    @multi_apply
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
            # delete the generated source so that we can regenerate it in the next iteration
            generated_file = generate.compound_properties[0].try_get_property('string')
            assert generated_file is not None
            generated_file = generated_file.associated_value
            if os.path.exists(generated_file):
                os.remove(generated_file)
            # delete the symbols defined by the generated file from the scope so that we can re-import them in the next iteration
            for defn in generate.compound_properties[2:]: # 0, 1 are output_file and prompt, the rest are definitions
                if defn.symbol.s in scope.local_vars:
                    del scope.local_vars[defn.symbol.s]
                elif defn.symbol.s in scope.local_defns:
                    del scope.local_defns[defn.symbol.s]
            
        raise CompileError(f'Conditions {args} exceeded retries, giving up')

@builtin_definition
class ConfigureDefinition(Definition):
    symbol = 'configure'
    property_names = ['generate']
    param_names = ['value'] # of the form `property generate configure(value)`
    @binary_apply
    def apply(self, lhs: Expression, rhs: Expression, scope: Scope) -> Expression:
        configuration[lhs.symbol.s] = expression_to_associated_value(rhs)
        return rhs