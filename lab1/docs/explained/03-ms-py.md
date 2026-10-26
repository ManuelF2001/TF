# 3 · `ms.py`, line by line

`code/ms.py` is the course's helper library (an unmodified copy of
`kit/ms.py`). We did not write it, but **every line of `d.py` depends on
how it behaves**: why handlers never run at the same time, how a reply finds
its callback, what a "crash" really does. In the final discussion,
"why don't you need locks?" and "what does a crashed node actually do?" are
questions about this file.

Why is there a copy in `code/`? When Python runs `code/d.py`, it adds the
script's own directory (`code/`) to the import path, so `from ms import …`
finds `code/ms.py`. Without the copy, the import fails.

Line numbers refer to `code/ms.py`.

---

## 1. Header (lines 1–21)

```python
# Minimal support for Maelstrom node programs
# Basic API ...:  send, reply, receiveAll, exitOnError
# Additions:      run, rpc, set_timeout / every, trace
# Crash injection: MS_CRASH="n1@5" ...
```

Documentation only. The important sentence is the last one: *"A crashed
node stays alive for Maelstrom but receives, sends and executes nothing."*

## 2. Imports (lines 23–30)

```python
import logging                                  # writes to stderr → node log
import threading                                # Lock, Timer
import time                                     # time.time() for traces, time.monotonic() for crashes
from os import environ, _exit                   # read MS_CRASH; hard-exit on errors
from sys import stdin, stderr                   # stdin = incoming network; stderr = log
from json import loads, dumps                   # JSON text <-> Python objects
from types import SimpleNamespace as sn         # object with attributes: msg.body.key
from concurrent.futures import ThreadPoolExecutor   # the single worker thread
```

- `SimpleNamespace` is an object whose attributes you can set freely:
  `sn(a=1).a == 1`. `ms.py` turns every JSON object into one, so you write
  `msg.body.key` instead of `msg['body']['key']`.
- `_exit` (with underscore) kills the process **immediately**, without
  cleanup. `sys.exit` would only raise an exception in the current thread.

## 3. Module state (lines 32–41)

```python
msg_id = 0          # counter for the msg_id of every message this node sends
node_id = None      # this node's name, set at init ("n1")
node_ids = []       # all node names, set at init (["n0","n1","n2"])
```

These are `ms.py`'s own variables. `d.py` keeps **its own** `node_id` /
`node_ids` (see `05-d-py.md`). `ms.py` needs them for `trace()` (the
`node` field) and for the crash schedule.

```python
executor = ThreadPoolExecutor(max_workers=1)
```

**The most important line for understanding concurrency.** A thread pool
with **one** worker thread. Every handler, every rpc callback and every
timer function is *submitted* to it, and the worker runs them **one at a
time, in the order they were submitted** (it keeps a first-in, first-out
queue). Consequences:

- two handlers never run at the same time, so node state (`store`) needs
  **no locks**;
- a handler must **never wait** for another message. The reply could only
  be processed after the current handler returns, so waiting would deadlock
  the node forever. That is why `rpc` takes a *callback*.

```python
_lock = threading.Lock()   # protects msg_id/_pending and keeps printed lines whole
_pending = {}              # msg_id of an rpc we sent → function to call with its reply
_t0 = None                 # monotonic time of init; crash times are relative to it
_down = []                 # list of (start, end) windows in which this node is "crashed"
```

The leading underscore is a Python convention for "internal, don't use from
outside".

## 4. The public API

### `send` (lines 43–44)

```python
def send(src, dest, **body):
    return _send(src, dest, body)
```

`**body` collects all keyword arguments into a dict:
`send('n0', 'n1', type='update', key=0, value=3)` gives
`body = {'type': 'update', 'key': 0, 'value': 3}`. Sends one message,
expects nothing back, returns the `msg_id` it used. **Fire and forget.**
`d.py` uses it for `update` messages.

### `reply` (lines 46–47)

```python
def reply(request, **body):
    return send(request.dest, request.src, in_reply_to=request.body.msg_id, **body)
```

Answers a received message:

- **source** = `request.dest`, the name the request was addressed to,
  which is our own name;
- **destination** = `request.src`, whoever sent the request;
- adds `in_reply_to` = the request's `msg_id`, so the sender can match it.

Example: n0 receives `{"src":"n1","dest":"n0","body":{"msg_id":2,…}}`.
`reply(msg, type='read_ok', value=4)` sends
`{"src":"n0","dest":"n1","body":{"msg_id":…,"in_reply_to":2,"type":"read_ok","value":4}}`.

Note: if `body` already contained a key `in_reply_to`, Python would raise
`TypeError: got multiple values for keyword argument 'in_reply_to'`. That
is why `d.py`'s `relay` removes it first (`05-d-py.md`).

### `rpc` (lines 49–53)

```python
def rpc(src, dest, callback, timeout=None, on_timeout=None, **body):
    mid = _send(src, dest, body, callback)      # send and remember callback under its msg_id
    if timeout is not None:
        set_timeout(timeout, _expire, mid, on_timeout)   # optional: give up after `timeout` s
    return mid
```

"Remote procedure call" without blocking: send a request, and **when** a
message with `in_reply_to == mid` arrives, call `callback(that_message)`
instead of the normal handler. The function returns at once; the reply
comes later (or never).

`d.py` calls `rpc(node_id, PRIMARY, relay, **request)` **without**
`timeout`. So if n0 never answers, `relay` is simply never called, and the
entry stays in `_pending` forever (harmless).

### `receiveAll` (lines 55–64)

```python
def receiveAll():
    while data := stdin.readline():
```

Read stdin line by line. `:=` (the "walrus" operator, Python 3.8+) assigns
and tests at once. `readline()` returns `''` only at end-of-file (Maelstrom
closed the pipe), and that ends the loop. Each line is one JSON message.

```python
        msg = loads(data, object_hook=lambda x: sn(**x))
```

Parse JSON. `object_hook` is called for **every** JSON object, inner ones
first, and replaces the dict with a `SimpleNamespace`. So both `msg` and
`msg.body` become objects: `msg.src`, `msg.body.type`, `msg.body.key`.

```python
        if getattr(msg.body, 'type', None) == 'init':
            _init(msg)
```

If this is the `init` message, set up `ms.py`'s state (node name, crash
schedule) **before** anything else. `getattr(obj, 'type', None)` returns
`None` instead of crashing if a body has no `type`.

```python
        if crashed():
            logging.debug("crashed, dropping received %s", data.strip())
            continue
```

**Crash injection, input side.** If we are inside a crash window, log it
and throw the message away: it is lost, not queued. You can see these lines
in `runs/p4-crash-n0/node-logs/n0.log`:

```
DEBUG:root:crashed, dropping received {"src":"n1","dest":"n0","body":{"msg_id":18,"key":0,"type":"read"}}
```

That is n1's forwarded read, dropped by the "crashed" n0.

```python
        logging.debug("received %s", data.strip())
        yield msg
```

Log the message (the `received …` lines in node logs) and hand it to the
caller. `yield` makes `receiveAll` a **generator**: the `for` loop in `run`
gets one message at a time as they arrive.

### `exitOnError` (lines 66–71)

```python
def exitOnError(fn, *args):
    try:
        fn(*args)
    except:
        logging.exception("fatal exception in handler")
        _exit(1)
```

Run `fn`. If **anything** goes wrong (a bare `except:` catches every
exception), print the traceback to the log and **kill the node**.

Why so drastic? An exception inside a `ThreadPoolExecutor` task is
otherwise silently stored and never shown. The node would keep running with
half-updated state, and the bug would be invisible. Dying loudly makes
Maelstrom report the failure, and the traceback is in `node-logs/`.

### `run` (lines 73–75)

```python
def run(handle):
    for msg in receiveAll():
        executor.submit(exitOnError, _dispatch, handle, msg)
```

The **main loop**, called by the last line of `kv.py` and `d.py`. The main
thread only **reads**. For each message it submits
`exitOnError(_dispatch, handle, msg)` to the single worker thread. So:

- the main thread is never blocked by a slow handler (it keeps reading);
- handlers run on the worker, **one at a time, in arrival order**.

Here is the guarantee n0 relies on: **n0 executes requests in a single
total order, one at a time.** That gives D its linearization points
(`01-theory.md` §9).

### `set_timeout` (lines 77–81)

```python
def set_timeout(seconds, fn, *args):
    timer = threading.Timer(seconds, lambda: executor.submit(exitOnError, _call, fn, *args))
    timer.daemon = True
    timer.start()
    return timer
```

Run `fn(*args)` after `seconds`. The `Timer` waits on its own thread, but
when it fires it does **not** run `fn` there. It *submits* it to the worker
thread, so timers also respect "one at a time". `daemon = True`: the timer
thread won't keep the process alive at exit. It returns the timer so you
can `.cancel()` it. **Not used by our code.**

### `every` (lines 83–87)

```python
def every(seconds, fn, *args):
    def tick():
        _call(fn, *args)
        set_timeout(seconds, tick)
    return set_timeout(seconds, tick)
```

Periodic timer: each `tick` runs `fn` and schedules the next `tick`.
(Detail: during a crash window `_call` skips `tick` itself, so the chain is
not rescheduled and stops for good.) **Not used by our code.**

### `trace` (lines 89–91)

```python
def trace(event, **fields):
    record = dict(t=round(time.time(), 6), node=node_id, event=event, **fields)
    print("TRACE " + dumps(record, default=vars), file=stderr, flush=True)
```

Write one structured event to the node log:

- `t`: wall-clock time in seconds, to the microsecond. `time.time()` is
  used (not `monotonic`) so `timeline.py` can compare it with times from
  other nodes and from `jepsen.log`; all nodes run on the same machine, so
  their clocks agree;
- `node`: `ms.py`'s `node_id`;
- `event` + whatever fields you pass (`key=0, op='read'`, …);
- `default=vars`: if a field is a `SimpleNamespace`, serialize its
  attributes;
- `file=stderr`: to the log, **never** stdout (stdout is the network);
- `flush=True`: write it now, not when a buffer fills.

The `TRACE ` prefix is what `kit/timeline.py` searches for. Note that
`trace` does **not** check `crashed()`. That is how the `crash` and
`recover` events can be printed. Handlers don't run while crashed anyway.

### `crashed` (lines 93–97)

```python
def crashed():
    if _t0 is None:
        return False                      # before init: never crashed
    elapsed = time.monotonic() - _t0      # seconds since init
    return any(start <= elapsed and (end is None or elapsed < end) for start, end in _down)
```

True if "now" is inside any crash window. `end is None` means "forever"
(crash-stop). `time.monotonic()` is a clock that never jumps backwards, so
it is safe for measuring intervals. Times are **relative to `init`**, so
`n0@5` means 5 s after this node was initialized, which is roughly 5 s into
the test.

## 5. Internals

### `_send` (lines 101–114): the only place a message leaves the node

```python
def _send(src, dest, body, callback=None):
    global msg_id
    with _lock:
```

`global msg_id` because we assign to the module variable. `with _lock:`
makes the whole block atomic with respect to other threads, so the counter
can't be incremented twice at once and two messages can't be printed mixed
up on one line.

```python
        msg_id += 1
        mid = msg_id
```

A fresh number for this message. Numbers are **per node** (n0 and n1 both
have a `msg_id 5`).

```python
        data = dumps(sn(dest=dest, src=src, body=sn(msg_id=mid, **body)), default=vars)
```

Build the envelope and turn it into one line of JSON. `default=vars` tells
`json` how to serialize a `SimpleNamespace` (as its attribute dict). Note
`sn(msg_id=mid, **body)`: if `body` already had a `msg_id` key, this would
be `TypeError: got multiple values for keyword argument 'msg_id'`. That is
**why `d.py`'s `forward` removes the client's `msg_id`** before passing the
body on.

```python
        if crashed():
            logging.debug("crashed, dropping sent %s", data)
            return mid
```

**Crash injection, output side.** While crashed, nothing leaves the node,
and the callback is not even registered.

```python
        if callback is not None:
            _pending[mid] = callback
```

For an `rpc`: remember "when the reply to `mid` arrives, call `callback`".
This is registered **before** printing, so the reply can never arrive
before the callback is known.

```python
        logging.debug("sending %s", data)
        print(data, flush=True)
    return mid
```

Log it (`sending …` lines), then print it to **stdout**. That *is* sending:
Maelstrom reads our stdout. `flush=True` is essential. When stdout is a
pipe, Python buffers output, and without flushing the message could sit in
the buffer indefinitely.

### `_dispatch` (lines 116–123): who handles an incoming message

```python
def _dispatch(handle, msg):
    if crashed():
        return
```

Check again, now on the worker thread. A message may have been received
just before the crash moment and queued; it must not run after it.

```python
    callback = _pending.pop(getattr(msg.body, 'in_reply_to', None), None)
```

Is this the reply to one of our rpcs? Take its `in_reply_to` (or `None` if
it's a request), and **remove** the matching callback from `_pending`.
`pop(key, None)` returns `None` if there is none. Removing guarantees a
callback runs **at most once**.

```python
    if callback is not None:
        callback(msg)        # reply to an rpc → run its callback (e.g. d.py's relay)
    else:
        handle(msg)          # anything else → the program's handler
```

So in `d.py`, n0's answers to a backup never reach `handle()`. They go
straight to `relay`. Everything else (client requests, `init`, `update`)
goes to `handle()`.

### `_call` (lines 125–127)

```python
def _call(fn, *args):
    if not crashed():
        fn(*args)
```

Timers don't fire while crashed.

### `_expire` (lines 129–131)

```python
def _expire(mid, on_timeout):
    if _pending.pop(mid, None) is not None and on_timeout is not None:
        on_timeout()
```

When an rpc's timeout fires: if the reply hasn't come (still pending),
forget the callback and call `on_timeout`. A reply arriving after that
would go to `handle()`. **Not used by `d.py`** (no timeouts).

### `_init` (lines 133–147): remember who we are, schedule crashes

```python
def _init(msg):
    global node_id, node_ids, _t0
    node_id = msg.body.node_id
    node_ids = msg.body.node_ids
    _t0 = time.monotonic()
```

Store the node's identity in `ms.py` and start the crash clock.

```python
    for spec in filter(None, environ.get('MS_CRASH', '').replace(' ', '').split(',')):
```

Read `MS_CRASH` (empty if unset), remove spaces, split on commas.
`filter(None, …)` drops empty strings, so an unset variable gives no specs.
`"n1@5-15,n2@8"` → `["n1@5-15", "n2@8"]`.

```python
        node, _, times = spec.partition('@')     # "n1@5-15" → "n1", "@", "5-15"
        if node != node_id:
            continue                             # a spec for another node: ignore
        start, _, end = times.partition('-')     # "5-15" → "5","-","15";  "5" → "5","",""
        start, end = float(start), (float(end) if end else None)
        _down.append((start, end))               # (5.0, 15.0) pause, or (5.0, None) crash-stop
```

Each node parses the **same** variable and keeps only its own windows. So
`MS_CRASH="n0@5"` makes n0 crash, while n1 and n2 ignore it.

```python
        _at(start, lambda: trace('crash'))
        if end is not None:
            _at(end, lambda: trace('recover'))
```

Schedule the `crash` / `recover` trace events, so you can see the exact
moment in `timeline.py`. These **only print**: the crash itself is
implemented by the `crashed()` checks, not by these timers.

### `_at` (lines 149–152)

```python
def _at(seconds, fn):
    timer = threading.Timer(seconds, fn)
    timer.daemon = True
    timer.start()
```

Like `set_timeout`, but runs `fn` directly on the timer thread, without the
worker and without the `crashed()` check. That is needed because the
`crash` event must be printed *at* the crash moment, when `_call` would
already refuse.

---

## 6. Summary: what a "crash" really is

With `MS_CRASH="n0@5"`, from 5 s after init, n0:

| | behaviour | line |
|---|---|---|
| incoming messages | read from stdin, logged as `crashed, dropping received`, discarded | 60–62 |
| messages already queued | discarded at dispatch | 117–118 |
| outgoing messages | not printed; logged as `crashed, dropping sent` | 107–109 |
| timers | don't run | 126 |
| memory (`store`) | **kept** (relevant only for pauses `n0@5-12`) | — |
| the process | **still alive** → Maelstrom doesn't notice | — |

From outside this is indistinguishable from a real crash. For a pause
(`n0@5-12`), from 12 s on everything works again with the old `store`, but
every message that arrived during the pause is gone forever.

## 7. Summary: the threading model

```
main thread:     readline → parse → (init?) → crashed? → submit ──┐
                 readline → parse → ...                  submit ──┤
                                                                   ▼
worker thread:   [ _dispatch(msg1) ] [ _dispatch(msg2) ] [ timer fn ] ...   one at a time, FIFO
                       │
                       ├─ reply to an rpc?  → callback(msg)
                       └─ otherwise         → handle(msg)

timer threads:   sleep N s → submit to worker
```

Every piece of **our** code (`handle`, `forward`, `relay`, `execute`,
`propagate`) runs on the single worker thread.
