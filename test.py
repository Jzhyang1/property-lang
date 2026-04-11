from definitions import CompileError
from main import tokenize, build_tree, Scope, global_definitions, resolve_expression

if __name__ == "__main__":
    from argparse import ArgumentParser
    argparser = ArgumentParser(description="Run a .lang file")
    argparser.add_argument('file', default='test.lang', help='the .lang file to run')
    args = argparser.parse_args()
    file = args.file

    tokenized = tokenize(file)    
    built, i = build_tree(tokenized)
    scope = Scope(local_defns=global_definitions)
    try:
        for expr in built:
            resolved = resolve_expression(expr, scope)
            print(expr, '->', resolved)
    except CompileError as e:
        pass

    print('----------')
    for var in scope.local_vars:
        print(scope.local_vars[var])