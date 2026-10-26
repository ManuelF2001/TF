# 4 · `kv.py`, line by line (Part 2: one server)

`code/kv.py` is the single-server key-value store. It answers every request
from its own dictionary and never talks to other nodes. It is worth
understanding well, because `d.py`'s `execute()` is the same logic, moved
to the primary.

Line numbers refer to `code/kv.py`.

---

## Line 1: the shebang

```python
#!/usr/bin/env python3
```

Maelstrom runs the program directly (`--bin code/kv.py`), not through
`python3 code/kv.py`. Linux reads this first line to know which interpreter
to use: `/usr/bin/env python3` means "find `python3` on the PATH". For this
to work the file must also be executable; `kit/run.sh` does `chmod +x` on
it. (The file must have Unix line endings. With Windows `\r\n`, the system
would look for an interpreter called `python3\r` and fail. Ours are fine.)

## Lines 3–8: comment

States what the program is: one dictionary per node, no communication;
correct with 1 node, wrong with several.

## Lines 10–11: imports

```python
import logging
from ms import reply, run, trace
```

- `logging`: for `logging.info` / `logging.warning`, which go to stderr, so
  to `node-logs/n0.log`.
- `reply`: answer a request (`03-ms-py.md` §4).
- `run`: the main loop.
- `trace`: structured events for `timeline.py`.
- Not imported: `send` and `rpc`. `kv.py` never sends a message on its own;
  it only answers. That alone shows the nodes don't coordinate.

## Line 13: log level

```python
logging.getLogger().setLevel(logging.DEBUG)
```

Python's root logger shows only WARNING and above by default. `ms.py` logs
every message as `logging.debug("received …")` / `("sending …")`, so this
line turns DEBUG on and makes those lines appear in the node logs. Without
it you would lose the most useful debugging information. (The first logging
call automatically sets up a handler writing to **stderr** with format
`LEVEL:logger:message`, which is why the log lines look like
`DEBUG:root:received {…}`.)

## Line 15: the state

```python
store = {}          # key -> value
```

The entire database: a Python dict from key (int) to value (int), in
memory. It is lost if the process dies (no disk). Module-level, so every
call of `handle` sees the same dict.

## Lines 17–19: the handler

```python
def handle(msg):
    global node_id, node_ids
    body = msg.body
```

- `handle(msg)` is called by `ms.py` for every incoming message that isn't
  an rpc reply, **one at a time** on the worker thread.
- `global node_id, node_ids`: we assign these names below, and without
  `global` Python would make them local variables of this call and forget
  them at the end. In `kv.py` they are only used for the log message; they
  are kept for symmetry with `d.py`, where they matter.
- `body = msg.body`: shorthand.

## Lines 21–25: `init`

```python
    if body.type == 'init':
        node_id = body.node_id          # e.g. "n0"
        node_ids = body.node_ids        # e.g. ["n0"] or ["n0","n1","n2"]
        logging.info('node %s initialized', node_id)
        reply(msg, type='init_ok')
```

Maelstrom's first message. We remember our name and the list of nodes, log
it, and answer `init_ok`. Maelstrom sends no client traffic until every
node has answered `init_ok`. If a node never answers, the test fails at
startup.

`logging.info('node %s initialized', node_id)` uses `%s` with a separate
argument (not an f-string) so the string is only formatted if the message
is actually logged. That is the standard logging idiom.

## Lines 27–31: `read`

```python
    elif body.type == 'read':
        if body.key in store:
            reply(msg, type='read_ok', value=store[body.key])
        else:
            reply(msg, type='error', code=20, text='key does not exist')
```

- Key present: answer `read_ok` with the value.
- Key never written: error **20**. The checker counts it as `fail` ("read
  did nothing"), which is the correct answer, not a bug. That is part of the
  `fail` count of every run.
- No `trace`: a read changes nothing, so we didn't trace it (`d.py` traces
  reads too).

## Lines 33–36: `write`

```python
    elif body.type == 'write':
        store[body.key] = body.value
        trace('write', key=body.key, value=body.value, client=msg.src)
        reply(msg, type='write_ok')
```

1. Overwrite the value (creates the key if new).
2. Trace it, with the client id (`msg.src`, e.g. `c6`), so `timeline.py`
   shows which write changed what.
3. Acknowledge.

A write never fails in this workload.

## Lines 38–48: `cas`

```python
    elif body.type == 'cas':
        expected = getattr(body, 'from')     # 'from' is a Python keyword
```

The request is `{"type":"cas","key":k,"from":a,"to":b}`. `body.from` is a
**syntax error** in Python (`from` is reserved: `from x import y`), so we
read the attribute by name with `getattr(body, 'from')`. `body.to` is fine.

```python
        if body.key not in store:
            reply(msg, type='error', code=20, text='key does not exist')
```

No such key: error 20, nothing changes.

```python
        elif store[body.key] != expected:
            reply(msg, type='error', code=22,
                  text=f'expected {expected}, found {store[body.key]}')
```

Current value isn't `from`: error **22** (precondition failed), nothing
changes. The `text` is for humans (it appears in `history.txt`). Most `cas`
operations end here, because values are random 0–4.

```python
        else:
            store[body.key] = body.to
            trace('cas', key=body.key, value=body.to, client=msg.src)
            reply(msg, type='cas_ok')
```

Value matches: set it to `to`, trace, acknowledge.

**Why this cas is atomic:** the check (`!=`) and the update happen in the
same handler call, and no other handler can run in between (single worker
thread). So two concurrent `cas(x, 1, …)` can't both see 1.

## Lines 50–51: anything else

```python
    else:
        logging.warning('unknown message type %s', body.type)
```

Defensive: log unexpected messages instead of crashing. In practice it is
never reached.

## Line 53: start

```python
run(handle)
```

Start `ms.py`'s main loop with our handler. It runs until Maelstrom closes
stdin at the end of the test. Everything above was only *definitions*; this
line is where the program actually starts working.

---

## Why `kv.py` is correct with one node

Every operation is handled in **one step** on **one thread**: read or
modify the dict, decide the answer, send it. The moment the handler runs is
after the request arrived (after the invocation) and before the reply left
(before the completion). That moment is the linearization point, and the
dict *is* the single register. Evidence: `runs/p2-single`, valid, 152 ok.

## What happens when it crashes (`MS_CRASH="n0@5"`)

`ms.py` makes n0 drop everything after 5 s (`03-ms-py.md` §6). The
handler never runs again, so no request is answered. Each client times out
after 1 s: reads become `fail`, writes/cas become `info`. **Valid** (no
wrong answer was ever given), **unavailable** (0 ok after 5 s). Evidence:
`runs/p2-single-crash`, valid, 33 ok / 25 fail / 15 info.

## Why it is wrong with three nodes

Nothing in the code uses `node_ids` or sends to another node, so each node
is a separate store. Client p3 writes 2 at n0, client p2 reads at n2 and
gets n2's old 0, after the write was acknowledged. That is a stale read.
Evidence: `runs/p2-independent`, **INVALID**, `linear.svg`: *"can't read 0
from register 2"*. (Full walk-through in `../02-single-server.md` §4.)

This is exactly what `d.py` fixes, by having only one dict that matters.
