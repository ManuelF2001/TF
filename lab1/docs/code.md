# Code walkthrough

The lab asks that **every member can explain every line**. This file goes
through all the code in `lab1/code/` and the scripts in `lab1/`.

| file | what it is |
|---|---|
| `code/ms.py` | unmodified copy of `kit/ms.py` (Python adds the script's own directory to the import path, so the copy must sit next to our programs) |
| `code/kv.py` | Part 2: single-server key-value node |
| `code/d.py` | Parts 3–4: strategy D, primary for everything |
| `scenarios.sh` | runs one scenario N times and records verdict + counts |
| `run_all.sh` | reruns every scenario cited in the documents |

---

## 1. What `ms.py` gives us (the parts we use)

- `run(handle)`: reads one JSON message per line from stdin and calls
  `handle(msg)` for each. **All handlers, rpc callbacks and timers run one at
  a time on a single thread**, so node state needs no locks, but a handler
  must never block waiting for another message.
- `msg` is a `SimpleNamespace`: `msg.src`, `msg.dest`, `msg.body.type`,
  `msg.body.key`, … ; `vars(msg.body)` turns the body back into a `dict`.
- `reply(request, **body)`: sends `body` to `request.src`, from
  `request.dest`, with `in_reply_to = request.body.msg_id`.
- `send(src, dest, **body)`: sends a message; nobody waits for an answer.
- `rpc(src, dest, callback, **body)`: sends a message and registers
  `callback`; when a message with `in_reply_to` equal to its `msg_id`
  arrives, `callback(reply)` runs instead of `handle`.
- `trace(event, **fields)`: writes a `TRACE {...}` line to the node log;
  `kit/timeline.py` merges these lines from all nodes in time order.
- Crash injection: with `MS_CRASH="n0@5"`, from 5 s after `init` node n0
  drops every message it receives or sends and runs no timers. The process
  stays alive, so Maelstrom does not notice: to everyone else n0 just
  falls silent.

---

## 2. `kv.py` — one server

```python
store = {}          # key -> value
```
The whole state: a Python dict. Keys and values are integers.

```python
if body.type == 'init':
    node_id = body.node_id
    node_ids = body.node_ids
    reply(msg, type='init_ok')
```
Maelstrom's first message tells the node its name and the names of all
nodes. The node must answer `init_ok` before it receives any client
requests.

```python
elif body.type == 'read':
    if body.key in store:
        reply(msg, type='read_ok', value=store[body.key])
    else:
        reply(msg, type='error', code=20, text='key does not exist')
```
A read returns the current value. A key that was never written gets error
20, which the checker records as a definite `fail`.

```python
elif body.type == 'write':
    store[body.key] = body.value
    trace('write', ...)
    reply(msg, type='write_ok')
```
A write overwrites the value and is acknowledged right away. The `trace`
line is only for `timeline.py`.

```python
elif body.type == 'cas':
    expected = getattr(body, 'from')
```
`from` is a Python keyword, so `body.from` is a syntax error; `getattr`
reads the field by name.

```python
    if body.key not in store:       -> error 20
    elif store[body.key] != expected: -> error 22 (precondition failed)
    else: store[body.key] = body.to; reply cas_ok
```
Compare-and-set: succeed only if the current value equals `from`.

**Why it is linearizable with one node:** the single thread runs one handler
at a time, and each handler reads/updates the dict and replies in the same
step. The linearization point of every operation is the moment its handler
runs, which is after the request arrived and before the reply was sent.

**Why it is not with three nodes:** `kv.py` never talks to other nodes
(`node_ids` is unused), so each node is a separate store. A client of n2
cannot see a write acknowledged by n0 (see `02-single-server.md`, §4).

---

## 3. `d.py` — strategy D

### State and constants

```python
PRIMARY = 'n0'
store = {}
```
The primary is fixed. Every node has a `store`, but only n0's copy is ever
used to answer clients; the backups' copies are kept up to date (best
effort) but never read.

### Dispatch

```python
elif body.type in ('read', 'write', 'cas'):
    if node_id == PRIMARY:
        execute(msg)
    else:
        forward(msg)
```
The same message types arrive from two kinds of senders: from clients
(`c6`, `c7`, …) and, at n0, from backups forwarding a client's request.
n0 does not need to tell them apart: it executes and replies to `msg.src`,
whoever that is. A backup forwards everything, reads included.

```python
elif body.type == 'update':
    store[body.key] = body.value
    trace('apply', ...)
```
Backups receive `update` messages from the primary and overwrite their copy.
There is no reply: the primary does not wait for acknowledgements.

### `forward(msg)` — at a backup

```python
request = {k: v for k, v in vars(msg.body).items() if k != 'msg_id'}
```
Copy the client's request body (`type`, `key`, and `value` or `from`/`to`)
without its `msg_id`, because `rpc` assigns a new `msg_id` for the hop to
n0. Copying the dict also passes the `from` field without having to name
it.

```python
def relay(response):
    result = {k: v for k, v in vars(response.body).items()
              if k not in ('msg_id', 'in_reply_to')}
    reply(msg, **result)
```
`relay` is the callback that runs when n0's answer arrives. It strips the
fields of the n0→backup hop and sends the rest (`read_ok` + `value`,
`write_ok`, `cas_ok`, or `error` + `code` + `text`) to the client, as a
reply to the client's original request (`msg`, captured by the closure).

```python
rpc(node_id, PRIMARY, relay, **request)
```
Send and return. The handler does not wait; the node keeps serving other
messages. **No timeout** is set: if n0 never answers, `relay` never runs and
the client's request is never answered; the client times out and records
`info`. (Replying error 11 after a timeout would be **wrong**: the backup
cannot know whether n0 executed the request, so the honest error would be 13,
"may or may not have happened". We chose not to add a timeout at all, to
keep to the strategy as stated.)

### `execute(msg)` — at the primary

Same logic as `kv.py`, with two differences:

1. After a successful `write` or `cas` it calls `propagate(key)` before
   replying.
2. `msg.src` may be a backup; the reply goes back to it and the backup
   relays it.

Reads and failed `cas` change nothing, so they propagate nothing.

### `propagate(key)`

```python
for dest in node_ids:
    if dest != node_id:
        send(node_id, dest, type='update', key=key, value=store[key])
```
Send the **new value** (state transfer) to every other node, fire and forget.
Because it sends the resulting value, a `cas` needs no special handling at
the backups: they never evaluate the condition.

What this does **not** guarantee (deliberately, it is not part of D):

- that a backup received the update (no ack, no retry; a crashed or
  partitioned backup misses it forever);
- that updates of the same key are applied in the order n0 executed them
  (Maelstrom may reorder messages; there are no sequence numbers).

So the backups' copies can be stale or even diverge from n0's. Under D this
is invisible, because nobody reads them. It would matter as soon as a backup
had to take over (Part 6, Q3).

### Trace events

| event | where | meaning |
|---|---|---|
| `forward` | backup | client request sent on to n0 |
| `execute` | n0 | operation executed on the authoritative copy — **the linearization point** |
| `propagate` | n0 | updates sent to the backups |
| `apply` | backup | update written into the backup's copy |
| `relay` | backup | n0's answer passed on to the client |
| `crash` | any | written by `ms.py` when `MS_CRASH` stops the node |

Show them with `../kit/timeline.py --history` (add `--key 0` or
`--process 3` to filter).

---

## 4. `scenarios.sh` and `run_all.sh`

`scenarios.sh <program> <scenario> [repeats]` maps a scenario name to the
`MS_CRASH` variable and the Maelstrom options of the Part 3 table, calls
`../kit/run.sh lin-kv <program> <options>`, and appends one line to
`results/results.tsv`:

```
program  scenario  verdict  ok  fail  info  run-directory
```

The verdict is taken from the last line of Maelstrom's output
(`Everything looks good!` → valid, otherwise INVALID). The counts come from
the `:stats` block of `store/latest/results.edn`. The run directory is
where `store/latest` pointed, so each line names the evidence it came from.

`run_all.sh` reruns every scenario cited in the documents
(`./run_all.sh part2` or `./run_all.sh part4` for half of them).

`--test-count 3` would also run a scenario three times, but `store/latest`
only points to the last run; looping in `scenarios.sh` records all three.
