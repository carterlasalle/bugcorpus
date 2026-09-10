# BC-000001 — stale snapshot reused after await

## Symptom
Request handler returns stale object state after a concurrent update.

## Root cause
`snapshot = get_snapshot()` is taken, the handler awaits other work, then
dereferences `snapshot`. Another task may invalidate the snapshot while
suspended.

## Violated invariant
Snapshot objects returned by snapshot acquisition calls may not be
dereferenced after a suspension point unless refreshed after the final await.
