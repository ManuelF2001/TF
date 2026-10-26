# 5 · `d.py`, line by line (Parts 3–4: strategy D)

> **D – Primary for everything.** Every request is forwarded to n0, which
> executes it and sends the update to the others.

`code/d.py` is 110 lines. This file explains every one, then follows real
messages from our runs through the code, and ends with the "what if we had
done X instead?" questions an examiner is likely to ask.

Before reading: `03-ms-py.md` §4–5 (how `reply`, `rpc` and the single
worker thread behave) and `04-kv-py.md` (the `execute` logic is the same as
`kv.py`).

---

## Part A: every line

### Line 1: shebang

```python
#!/usr/bin/env python3
```

Same as `kv.py`: Maelstrom executes the file directly; Linux uses this line
to start `python3`.

### Lines 3–19: the design, written down

```python
# Lab 1, Parts 3-4: strategy D, "primary for everything".
#
# Every client request (read, write, cas) is forwarded to a fixed primary,
# n0. The primary executes it on its copy, sends the resulting value of
# the key to all other servers (fire and forget: it does not wait for
# acknowledgements) and replies. The server that received the request
# relays the primary's reply to the client.
#
# Decisions for the details the strategy leaves open:
#   - what is sent: the new value of the key (state), not the operation;
#     reads and failed cas change nothing, so they send no update.
#   - an update is applied on arrival by overwriting the key; there is no
#     acknowledgement and no ordering between updates.
#   - cas is executed only at the primary, like everything else.
#   - a backup never answers from its own copy and has no timeout: if the
#     primary does not answer, the client's request is never answered.
# There is no failover: if n0 stops, no server can complete operations.
```

This is the answer to Part 3, question 2 ("decide the details your strategy
leaves open"), kept in the code so whoever reads it knows *why* it is
written this way. Each decision maps to specific lines below.

### Lines 21–22: imports

```python
import logging
from ms import send, reply, rpc, run, trace
```

Compared with `kv.py` there are two more:

- `send`: fire-and-forget messages, used by the primary for `update`s;
- `rpc`: request + callback, used by the backups to forward to n0.

Not imported: `set_timeout`, `every`. **D has no timers at all.** This is
the code form of "no timeout, no retry, no failure detection".

### Line 24: log level

```python
logging.getLogger().setLevel(logging.DEBUG)
```

Show `ms.py`'s `received …` / `sending …` debug lines in the node logs
(`04-kv-py.md`, line 13).

### Lines 26–27: constants and state

```python
PRIMARY = 'n0'
store = {}          # key -> value (on the primary: the authoritative copy)
```

- `PRIMARY = 'n0'`: the primary is **fixed** and every node knows it in
  advance. There is no election and nothing can change it at run time.
  That is why there is no failover. Uppercase is the Python convention for
  a constant.
- `store = {}`: every node has one, but they play different roles:
  - on **n0** it is **the** database: every answer comes from it;
  - on **n1/n2** it is a passive copy that receives updates and is **never
    read** by any code path. (Search the file: `store[...]` is read only in
    `execute` and `propagate`, and both run only on n0.)

### Lines 29–31: the handler

```python
def handle(msg):
    global node_id, node_ids
    body = msg.body
```

Called by `ms.py` for every incoming message **except** replies to our own
`rpc`s, which go to their callback (`03-ms-py.md`, `_dispatch`).

`global node_id, node_ids`: these are `d.py`'s own module variables (not
`ms.py`'s, which are separate names in another module). We need `global`
because we *assign* them in the `init` branch. Functions that only *read*
them (`forward`, `propagate`) don't need it.

### Lines 33–37: `init`

```python
    if body.type == 'init':
        node_id = body.node_id
        node_ids = body.node_ids
        logging.info('node %s initialized', node_id)
        reply(msg, type='init_ok')
```

Learn who we are (`'n1'`) and who everyone is (`['n0','n1','n2']`).
`node_id` decides the role (line 40); `node_ids` gives the list of backups
to update (line 105). Same as `kv.py`.

### Lines 39–43: the core of strategy D, one `if`

```python
    elif body.type in ('read', 'write', 'cas'):
        if node_id == PRIMARY:
            execute(msg)
        else:
            forward(msg)
```

Any client request:

- **on n0** → execute it locally;
- **on any other node** → forward it to n0.

Note what is **not** here: no special case for reads. Strategy C would put
`if body.type == 'read': answer from own store` here. D forwards reads too,
and **that is what makes D linearizable**: no answer ever comes from a
backup's copy.

Also note that at n0 the same branch catches two kinds of senders:

- a **client** of n0 (`msg.src = 'c6'`);
- a **backup** forwarding a client's request (`msg.src = 'n1'`).

n0 doesn't need to tell them apart. It executes and replies to `msg.src`,
whoever that is (lines 68–71 say this in a comment).

`body.type in ('read', 'write', 'cas')` tests membership in a tuple: it is
true for any of the three.

### Lines 45–48: receiving an update (backups only)

```python
    elif body.type == 'update':
        # Sent by the primary: overwrite our copy with the new value.
        store[body.key] = body.value
        trace('apply', key=body.key, value=body.value)
```

When n0 propagates, each backup overwrites its copy and traces `apply`.

What it **doesn't** do, deliberately (design decision "no acknowledgement
and no ordering"):

- **no reply**: n0 doesn't wait for one, so none is sent;
- **no check of order**: if `update(x,1)` and `update(x,2)` arrive in the
  wrong order (Maelstrom may reorder), the backup ends with the old value 1;
- **no recovery of missed updates**: if the backup was crashed or
  partitioned when an update was sent, that update is gone.

So backup copies can be stale or wrong. Under D this is **invisible**
(nobody reads them). Proof that it happens: `runs/p4-partition` ends with
n2 = 4 while n0 = 3 (`../05-explain-execution.md`).

n0 never receives `update` (it doesn't send to itself, line 106).

### Lines 50–51: anything else

```python
    else:
        logging.warning('unknown message type %s', body.type)
```

Defensive logging. Never reached in our runs.

---

### Lines 53–66: `forward` (runs on a backup)

```python
def forward(msg):
    # Backup: send the same request to the primary, and relay its reply to
    # the client when (if) it arrives. The handler returns immediately.
```

`msg` is the client's original request, e.g.
`{"src":"c10","dest":"n1","body":{"key":0,"value":2,"type":"write","msg_id":1}}`.

#### Line 56: copy the request body, without its `msg_id`

```python
    request = {k: v for k, v in vars(msg.body).items() if k != 'msg_id'}
```

- `vars(msg.body)` gives the namespace's fields as a dict:
  `{'key': 0, 'value': 2, 'type': 'write', 'msg_id': 1}`.
- The dict comprehension builds a **new** dict with every field except
  `msg_id`: `{'key': 0, 'value': 2, 'type': 'write'}`.

Why remove `msg_id`? There are two reasons.

1. **It would crash.** `rpc` → `_send` builds `sn(msg_id=mid, **body)`
   (`ms.py` line 106). If `body` also contained `msg_id`, Python raises
   `TypeError: got multiple values for keyword argument 'msg_id'`.
   `exitOnError` would then kill the node.
2. **It belongs to another conversation.** The client's `msg_id 1` numbers
   the *client→n1* exchange. The *n1→n0* exchange needs n1's own fresh
   number, which `_send` assigns.

Why copy *all* the other fields instead of naming them? Because it works
for all three request types at once (`value` for write, `from`/`to` for
cas, nothing for read), and it avoids writing `from` by hand, which can't
be done in Python syntax.

#### Line 57: trace

```python
    trace('forward', key=msg.body.key, op=msg.body.type, client=msg.src)
```

Event `forward` with the **client id** (`c10`), which is the bridge between
`timeline.py --history`'s process numbers and our node events.

#### Lines 59–64: `relay`, the callback

```python
    def relay(response):
        result = {k: v for k, v in vars(response.body).items()
                  if k not in ('msg_id', 'in_reply_to')}
        trace('relay', key=msg.body.key, op=msg.body.type, client=msg.src,
              result=result['type'])
        reply(msg, **result)
```

A function **defined inside** `forward`. It runs later, when n0's answer
arrives (`ms.py` finds it in `_pending` by `in_reply_to`).

**Closure:** `relay` uses `msg`, a variable of `forward`. Python keeps it
alive for `relay` even after `forward` has returned. Each call of `forward`
creates a *new* `relay` remembering *its own* client request. That is how,
with many requests in flight, each answer goes back to the right client.

Line by line:

- `response` is n0's message to us, e.g.
  `{"src":"n0","dest":"n1","body":{"msg_id":19,"in_reply_to":6,"type":"write_ok"}}`.
- Line 60–61: copy the body without `msg_id` (n0's numbering) and
  `in_reply_to` (which pointed to n1's forward, number 6). What's left is
  the actual answer: `{'type': 'write_ok'}`, or
  `{'type': 'read_ok', 'value': 4}`, or
  `{'type': 'error', 'code': 22, 'text': '…'}`.
  Removing them is again necessary: `reply` adds its own `in_reply_to`
  and `_send` its own `msg_id`, and duplicates would be a `TypeError`.
- Line 62–63: trace `relay` with the result type.
- Line 64: `reply(msg, **result)` answers the **client's original
  request**: destination `msg.src` = `c10`, `in_reply_to` = the client's
  `msg_id` 1. The client gets exactly n0's answer, as if n1 had produced it.

#### Line 66: send it

```python
    rpc(node_id, PRIMARY, relay, **request)
```

Send the request to n0 as an rpc whose callback is `relay`.

- `node_id`: `d.py`'s own name, e.g. `'n1'`, used as the source.
- `**request` expands the dict into keyword arguments
  (`type='write', key=0, value=2`), which `rpc` collects back into the
  message body. The key `'from'` works here because it's a dict key, not
  written as a keyword in the source.
- **No `timeout=`**: if no answer ever comes, `relay` is never called and
  the client never gets a reply. The client's own 1 s timeout then records
  `info` (write/cas) or `fail` (read). This is the design decision "a
  backup has no timeout".

Then `forward` returns, `handle` returns, and the node is free to process
the next message. **The backup doesn't wait.** Many forwarded requests can
be in flight at the same time, each with its own `relay`.

---

### Lines 68–102: `execute` (runs on n0 only)

```python
def execute(msg):
    # Primary: execute on the authoritative copy, propagate, reply.
    # msg.src is either a client (request sent directly to n0) or a backup
    # that forwarded it; the reply goes back to whoever sent it.
    body = msg.body
    key = body.key
```

This is `kv.py`'s logic with two additions: **trace every execution**, and
**propagate** after every change. The moment this function runs is the
**linearization point** of the operation (`01-theory.md` §9).

#### Lines 75–81: read

```python
    if body.type == 'read':
        if key in store:
            trace('execute', key=key, op='read', value=store[key], src=msg.src)
            reply(msg, type='read_ok', value=store[key])
        else:
            trace('execute', key=key, op='read', value=None, src=msg.src)
            reply(msg, type='error', code=20, text='key does not exist')
```

Answer from **n0's** store. Reads change nothing, so there is **no
propagate**. The trace records the value read and `src` (client id or
backup name), so in `timeline.py` you can see whether a request came
directly (`src="c6"`) or was forwarded (`src="n1"`). `value=None` is
written as `null` in the JSON trace.

#### Lines 83–87: write

```python
    elif body.type == 'write':
        store[key] = body.value
        trace('execute', key=key, op='write', value=body.value, src=msg.src)
        propagate(key)
        reply(msg, type='write_ok')
```

The order is: **update → trace → propagate → reply.**

- Update before reply: required. We must not acknowledge something we
  haven't done.
- Propagate before reply: chosen, but it **makes no difference to
  correctness**, because propagation is fire-and-forget (we don't wait) and
  backups are never read. Swapping the two lines would give identical
  results. It would only matter if n0 *waited* for acknowledgements, as in
  strategy B.

#### Lines 89–102: cas

```python
    elif body.type == 'cas':
        expected = getattr(body, 'from')     # 'from' is a Python keyword
        if key not in store:
            trace('execute', key=key, op='cas', result='missing', src=msg.src)
            reply(msg, type='error', code=20, text='key does not exist')
        elif store[key] != expected:
            trace('execute', key=key, op='cas', result='mismatch', src=msg.src)
            reply(msg, type='error', code=22,
                  text=f'expected {expected}, found {store[key]}')
        else:
            store[key] = body.to
            trace('execute', key=key, op='cas', value=body.to, src=msg.src)
            propagate(key)
            reply(msg, type='cas_ok')
```

Same three cases as `kv.py`: missing (20), mismatch (22), success. Only a
**successful** cas changes the value, so only it propagates.

The design decision "cas is executed only at the primary" is visible here.
The comparison `store[key] != expected` is done **once**, on **n0's**
copy, with no other handler running in between. Two concurrent
`cas(x, 1, …)` from clients of different backups both arrive at n0, are
executed one after the other, and the second one sees the first one's
result. At most one succeeds, as on a real register.

---

### Lines 104–108: `propagate` (runs on n0 only)

```python
def propagate(key):
    for dest in node_ids:
        if dest != node_id:
            send(node_id, dest, type='update', key=key, value=store[key])
    trace('propagate', key=key, value=store[key])
```

- Loop over all nodes from `init` (`['n0','n1','n2']`), skip ourselves.
- `send` (not `rpc`): **fire and forget**, nobody waits for an answer.
- The message carries the key's **new value** (`store[key]`), not the
  operation. This is **state transfer**. That is why a backup applies a
  successful cas just like a write: it receives "x is now 3", never
  "cas x from 1 to 3", so it never has to evaluate a condition.
- One `propagate` trace after the loop (not one per backup), so the trace
  shows when n0 *sent* updates. Each backup's `apply` trace shows when (or
  whether) it *received* one.

Works for any number of nodes: with `--node-count 5` it would send 4
updates.

### Line 110: start

```python
run(handle)
```

Start the main loop (`03-ms-py.md`, `run`). Same program on all three
nodes. Which role a node plays is decided at run time by line 40, from the
name it received in `init`.

---

## Part B: real messages through the code

### Flow 1: a client of n0 (no forwarding)

From `runs/p4-nofaults/node-logs/n0.log`:

```
received {"src":"c6","dest":"n0","body":{"key":0,"type":"read","msg_id":2}}
sending  {"dest":"c6","src":"n0","body":{"msg_id":8,"in_reply_to":2,"type":"read_ok","value":0}}
```

`handle` → line 40 (`node_id == 'n0'`) → `execute` → lines 76–78 → `reply`
to `c6`. Two messages, no server hops. Median latency 2 ms.

### Flow 2: a forwarded write (client c10 of n1), real logs

All lines are from `runs/p4-nofaults/node-logs/`, in time order (times are
the `t` of the traces, in seconds after …822.2):

```
n1  received  {"src":"c10","dest":"n1","body":{"key":0,"value":2,"type":"write","msg_id":1}}
n1  TRACE     forward  key=0 op=write client=c10                         .236964   ← line 57
n1  sending   {"dest":"n0","src":"n1","body":{"msg_id":6,"key":0,"value":2,"type":"write"}}   ← line 66
n0  received  {"src":"n1","dest":"n0","body":{"msg_id":6,"key":0,"value":2,"type":"write"}}
n0  TRACE     execute  key=0 op=write value=2 src=n1                     .238607   ← line 85  (linearization point)
n0  sending   {"dest":"n1","src":"n0","body":{"msg_id":17,"type":"update","key":0,"value":2}}  ← line 107
n0  sending   {"dest":"n2","src":"n0","body":{"msg_id":18,"type":"update","key":0,"value":2}}  ← line 107
n0  TRACE     propagate key=0 value=2                                    .238813   ← line 108
n0  sending   {"dest":"n1","src":"n0","body":{"msg_id":19,"in_reply_to":6,"type":"write_ok"}}  ← line 87
n1  received  {"src":"n0","body":{"msg_id":17,"type":"update","key":0,"value":2}}
n1  TRACE     apply    key=0 value=2                                     .239604   ← line 48
n2  received  {"src":"n0","body":{"msg_id":18,"type":"update","key":0,"value":2}}
n2  TRACE     apply    key=0 value=2                                     .239784   ← line 48
n1  received  {"src":"n0","body":{"msg_id":19,"in_reply_to":6,"type":"write_ok"}}  → ms.py finds relay in _pending[6]
n1  TRACE     relay    key=0 op=write client=c10 result=write_ok         .240006   ← line 62
n1  sending   {"dest":"c10","src":"n1","body":{"msg_id":7,"in_reply_to":1,"type":"write_ok"}}  ← line 64
```

Check the numbers:

- c10's `msg_id 1` → n1 forwards as `msg_id 6` → n0 replies
  `in_reply_to 6` → `ms.py` pops `_pending[6]` = this `relay` → n1 replies
  to c10 with `in_reply_to 1`.
- n0 sent the `update` (17) **before** the `write_ok` (19), and here n1
  happened to receive them in that order too. That isn't guaranteed and
  doesn't matter.
- Total time n1-forward → n1-relay: **3 ms** with no latency injected.

Space-time diagram:

```
c10        n1                      n0 (primary)                n2
 │──write──►│                        │                          │
 │          │──write (msg 6)────────►│                          │
 │          │                        X execute x=2  ← lin. point│
 │          │◄──update (17)──────────│──update (18)────────────►│ apply x=2
 │          │ apply x=2              │                          │
 │          │◄──write_ok (in_reply 6)│                          │
 │◄─write_ok│ relay                  │                          │
```

### Flow 3: a forward that is lost (partition)

From `runs/p4-partition` (`../05-explain-execution.md`), after the
partition `n0 | n1 n2` at 11.144 s:

```
12.298  p5   invoke   write [0 4] -> n2
12.299  n2   forward  key=0 op="write" client="c9"     ← line 57, then line 66 sends to n0
            (Maelstrom drops the message: n0 is on the other side)
            no execute at n0, no relay at n2, ever
13.298  p5   info     write [0 4] :net-timeout         ← the client's 1 s timeout
```

In the code: `rpc` registered `relay` in n2's `_pending`, but no reply ever
arrives, so `relay` never runs and line 64 is never reached. n2 doesn't
answer "error" because there is no timer (no `set_timeout` import). The
client decides on its own after 1 s, and because it is a write it records
`info`. It can't know that the write was never executed.

### Flow 4: the forward arrives, the reply is lost (asymmetric partition)

From `runs/p4-partition-2`:

```
3.210  p16  invoke   write [0 3] -> n1
3.211  n1   forward  key=0 op="write" client="c8"
3.212  n0   execute  key=0 op="write" value=3 src="n1"    ← executed! (line 84–85)
3.212  n0   propagate key=0 value=3                        write_ok to n1 is then dropped
3.293  p0   ok       read [0 3]                            ← another client sees it
4.210  p16  info     write [0 3] :net-timeout             ← its own client never learns
```

Same code path as flow 2 up to line 87, but n0's reply to n1 is dropped,
so `relay` never runs. The write **took effect** but the client recorded
`info`. The checker places it before p0's read, and the run is valid.

### Flow 5: n0 crashed (`MS_CRASH="n0@5"`)

```
n0.log:  crashed, dropping received {"src":"n1","dest":"n0","body":{"msg_id":18,"key":0,"type":"read"}}
```

n1 forwards (line 66), and `ms.py` on n0 drops the request (line 60–62 of
`ms.py`). `execute` never runs, so nothing is relayed, so every client
times out. 0 `ok` after 5 s, at all three servers. Valid.

---

## Part C: which line causes which result

| observed result | caused by |
|---|---|
| **always valid** | line 40–43 (only n0 executes) + no code path reads a backup's `store` + `ms.py`'s single worker thread |
| clients of backups ~2 hops slower (≈108 ms vs 8 ms with `--latency 50`) | line 66 (forward) + line 64 (relay): 2 extra server↔server messages |
| n0 crashes → **nobody** gets answers | line 26 (`PRIMARY` fixed) + line 66 without `timeout` + no failover code |
| n1 crashes → only n1's clients affected | line 107 is `send`, not `rpc`: n0 never waits for n1 |
| partition → cut-off clients get `info` / `fail` | line 66 forward lost, or n0's reply lost; no timeout to answer instead |
| backups diverge silently (n2 = 4, n0 = 3) | lines 45–48: no ack, no order, no catch-up; lines 104–108: no retry |
| at most one of two concurrent `cas(x,1,…)` succeeds | lines 94–101 run only on n0, one at a time |

---

## Part D: "what if…?" questions about the design

These are the questions most likely to come up in the individual
discussion. Each answer says what would change in the **code** and in the
**results**.

**1. What if a backup answered reads from its own copy?**
Change lines 39–43 to answer `read` locally on backups. That is strategy C.
Reads would be faster and would survive n0's crash, but a read at n2 right
after a write acknowledged by n0 could return the old value (the update is
still in flight, lost, or applied out of order). We'd expect **invalid**
runs, especially with `--latency` or partitions.

**2. What if the backup had a timeout and answered error 11?**
`rpc(..., timeout=1, on_timeout=lambda: reply(msg, type='error', code=11))`.
That would be **wrong**: 11 means "surely not done", but n0 may have
executed it with only the reply lost (flow 4). The checker would drop a
write that some other client then reads, and the run would be **invalid**.
Error **13** ("maybe") would be honest. It would only change when the
client learns about the failure, not correctness or availability.

**3. What if n0 waited for acknowledgements from the backups before
replying?**
Backups would have to reply to `update` (line 48), and n0 would need to
keep the client's request pending and reply from an rpc callback (it
**can't** wait in a loop: single thread, deadlock). If n0 waited for
*all*, then one crashed backup would block every write: the B problem. The
gain would be that an acknowledged write is guaranteed to be on the backups
too, which is the first step towards safe failover.

**4. Why send the value instead of the operation?**
With the operation (`cas x 1→3`), each backup would have to re-execute it,
and it gets the same result only if it executes the same operations **in
the same order** as n0. Maelstrom may reorder messages and there are no
sequence numbers, so backups could disagree about whether a cas succeeded.
With the value, a backup just overwrites. It can still end up stale
(reordering), but it never has to "decide" anything.

**5. Why does the reordering of updates not break correctness?**
Because no code path reads a backup's `store`. Wrong data that is never
read can't produce a wrong answer.

**6. Why are no locks needed, if many requests are in flight at once?**
"In flight" means waiting in the network or in `_pending`. The *code* runs
on one worker thread, one message at a time (`ms.py` line 36). `execute`
runs from start to end without interruption, so the check-and-set of cas is
atomic.

**7. Why can't `forward` just wait for n0's answer and then reply?**
Because the answer can only be processed by the same single worker thread
*after* `forward` returns. Waiting would block that thread forever
(deadlock). That is why `rpc` takes a callback and `relay` is a closure.

**8. What if two backups forwarded concurrent writes to the same key?**
n0 receives them in some order and executes them one after the other. That
order is the linearization order, and both clients get correct answers.
The backups might receive the two `update`s in the opposite order and keep
the "wrong" final value, which is invisible again (Q5).

**9. What if n0 came back after a pause (`n0@5-12`)?**
`ms.py` keeps memory, so n0's `store` is intact and service resumes
(observed in `runs/p4-pause-n0`: first `ok` at 12.688 s). Requests sent
during the pause are lost, not queued, so they end as `info`/`fail`. If n0
came back **without** memory (amnesia), it would answer `read` with
"key does not exist" or an old value after acknowledged writes: **invalid**.
`ms.py` can't simulate that.

**10. Could we make n1 take over when n0 is down?**
Not safely with this code. n1's copy may miss acknowledged writes (n0
doesn't wait for acks) or hold them out of order (no sequence numbers), and
n1 can't distinguish "n0 crashed" from "n0 is partitioned and still
serving" (split brain). See `01-theory.md` §11.

**11. Does it work with more nodes?**
Yes, unchanged: `node_ids` comes from `init`, `propagate` loops over it,
and `PRIMARY` stays `'n0'`. Same properties: correct, and as available as
n0.

**12. Why is `trace('execute', …)` the most important trace?**
It marks the linearization point. Listing the `execute` events in order
gives the single sequential history the checker looks for.
