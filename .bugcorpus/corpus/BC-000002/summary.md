# BC-000002 — raw eval on request-supplied expression

## Symptom
Attacker-controlled string is executed as code.

## Root cause
`eval()` is called on a non-constant value without a safe evaluator.

## Violated invariant
Code must never call eval/exec on a value that is not a static literal.
