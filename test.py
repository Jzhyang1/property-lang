from main import tokenize, build_tree, Scope, global_definitions, resolve_expr

if __name__ == "__main__":
    from argparse import ArgumentParser
    argparser = ArgumentParser(description="Run a .lang file")
    argparser.add_argument('file', default='test.lang', help='the .lang file to run')
    args = argparser.parse_args()
    file = args.file

    tokenize(file)
    built, i = build_tree(tokenize(file))
    scope = Scope(local_defns=global_definitions)
    for expr in built:
        resolved = resolve_expr(expr, scope)
        print(expr, '->', resolved)
    
    print('----------')
    for var in scope.local_vars:
        print(scope.local_vars[var])