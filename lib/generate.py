import os
from typing import Any
from constants import Definition, Scope, Expression, Property, Token
import constants
from definitions import register_definition, import_raw_python_file, expression_to_associated_value
from errors import perror, pwarning

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


@register_definition('generate', ['string', 'python'], [('prompt', ['string']), 'generate_signatures...'])
def generate_definition(lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
    rhs, *args = args
    output_file, prompt = lhs.force_get_property('string'), rhs.force_get_property('string')
    output_file, prompt = output_file.associated_value, prompt.associated_value
    cache_file = f'cache/generator/{output_file}.log'

    imports = [defn.symbol.s for defn in args]
    if os.path.exists(output_file) and os.path.exists(cache_file):
        # We cached the previous prompt in the file so that we can decide when to use
        # a cached version of the generator output, and when to call the generator again.
        with open(cache_file, 'r') as f:
            previous = f.read()
        if previous == prompt:
            import_raw_python_file(lhs, output_file, imports, scope)
            return lhs
    
    # We need to generate the output source from scratch
    generate_file(output_file, prompt)
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w') as f:
        f.write(prompt)
    # then we create load the generated source and add definitions to `scope`
    import_raw_python_file(lhs, output_file, imports, scope)
    return lhs

@register_definition('check', ['generate'], ['conditions...'])
def check_definition(lhs: Expression, args: list[Expression], scope: Scope) -> Expression:
    generate = lhs.try_get_property('generate')
    assert generate is not None
    # Get to the associated generator definition
    properties = []
    for p in lhs.properties:
        properties.append(p)
        if p == generate: break
    new_lhs = Expression(lhs.symbol, properties)
    from main import expression_resolve_all, resolve_last_property
    # repeat until all checks pass
    for _ in range(10): # max 10 iterations to prevent infinite loops
        resolved = resolve_last_property(new_lhs, scope, [])

        for condition in args:
            condition_evaluated = expression_resolve_all(condition, scope, constants.resolve)
            val = condition_evaluated.force_get_property('integer')
            if val.associated_value == 0:
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
    perror(f'Conditions {args} exceeded retries, giving up', anchor=lhs)

@register_definition('configure', ['generate'], ['value'])
def configure_definition(lhs: Expression, rhs: Expression) -> Expression:
    configuration[lhs.symbol.s] = expression_to_associated_value(rhs)
    return rhs