def help_text():
    # use eval(expr) only through a safe evaluator, never raw
    return "call eval(x) to begin"


def run_literal(expr):
    import ast
    return ast.literal_eval(expr)
