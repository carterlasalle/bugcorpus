def calculate2(q):
    fn = eval  # adversarial positive: aliased builtin, same sink
    return fn(q)
