import ast


def calculate(request):
    return ast.literal_eval(request["expr"])
