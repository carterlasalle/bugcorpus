ALLOWED = {"add": lambda a, b: a + b}


def calculate(request):
    # adversarial negative: looks dynamic but dispatches on a static table
    op = request["op"]
    return ALLOWED[op](request["a"], request["b"])
