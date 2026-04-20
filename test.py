from definitions import CompileError
from constants import resolve
from main import tokenize, build_tree, Scope, global_definitions, expression_resolve_all

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
            preprocessed = expression_resolve_all(expr, scope, resolve)
            print(expr, '->', preprocessed)
    except CompileError as e:
        print("Compile error:", e)

    print('----------')
    for var in scope.local_vars:
        print(scope.local_vars[var])