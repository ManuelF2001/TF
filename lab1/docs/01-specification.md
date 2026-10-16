# Part 1 – Specify the service

Workload: Maelstrom `lin-kv`. Messages (from `kit/AGENTS.md`):

| request | reply |
|---|---|
| `{"type":"read","key":k}` | `{"type":"read_ok","value":v}` |
| `{"type":"write","key":k,"value":v}` | `{"type":"write_ok"}` |
| `{"type":"cas","key":k,"from":a,"to":b}` | `{"type":"cas_ok"}` |

Errors: `{"type":"error","code":c,"text":...}` with 11 temporarily
unavailable (surely not done), 13 crash (maybe done), 20 key does not exist,
22 precondition failed.

## 1. Specification

### Single client (one operation at a time)

The store behaves as one map, each key a register, operations executed in
the order the client issues them:

- `read(k)` → `read_ok(v)` where `v` is the value of the **last** successful
  `write(k, v)` or `cas(k, _, v)` before it; error 20 if there was none.
- `write(k, v)` → `write_ok`; afterwards the value of `k` is `v`.
- `cas(k, a, b)` → if `k` does not exist: error 20, nothing changes; if the
  current value is `a`: `cas_ok` and the value becomes `b`; otherwise error
  22 and nothing changes.
- Every error reply means the operation had **no effect**, except 13.

### Several clients

The store must be **linearizable** (`theory.md` §2): each operation takes
effect atomically at one instant between its invocation and its response,
and the responses are those of the single-client specification applied in
the order of those instants.

- **A read concurrent with `write(k, v)`** (their intervals overlap) may
  return either the previous value or `v`. Both are allowed.
- **A read that starts after `write(k, v)` was acknowledged** must return
  `v`, or the value of a write/cas that took effect after it. Never an
  older value.
- **No going back:** if a read has returned `v`, any read that starts after
  it ends must also return `v` or newer — even if the first read was
  concurrent with the write.
- **cas is atomic:** of several concurrent `cas(k, a, …)` on value `a`, at
  most one succeeds.
- An operation whose client got no answer (`info`) may have taken effect or
  not; if it took effect, it did so after its invocation.

## 2. Assumptions

- **Servers:** 1 (Part 2), then 3 (`n0`, `n1`, `n2`), each with a full copy.
- **Clients:** 2 logical clients per server; each sends one request at a
  time and always talks to the same server.
- **Faults:**
  - servers fail by **crash-stop** (`MS_CRASH="n0@5"`): a crashed server
    sends, receives and executes nothing, and never recovers;
  - the network can **delay** messages arbitrarily (`--latency`) and
    **reorder** them; it does not corrupt, duplicate or invent them;
  - the network can be **partitioned** between servers (`--nemesis
    partition`): messages across the cut are lost while it lasts;
  - no Byzantine behaviour; state is in memory only.
- **Timing:** asynchronous — no bound on message delay or processing time
  that a server could rely on. Clients give up on a request after a timeout
  and record its outcome as unknown.

## 3. First claim (before any evidence)

> *Under* the assumptions above, with 3 servers running strategy D (all
> requests executed by n0), *if at most* f = 0 servers *fail by* crashing and
> the network delivers every message, *the service guarantees*
> linearizability of `read`, `write` and `cas` and that every request is
> eventually answered.
> *Even if* any servers crash or the network is partitioned, it still
> guarantees linearizability (but not that requests are answered).
> *Evidence:* — (none yet)
> *Not covered:* availability when n0 crashes; recovery of crashed servers;
> loss of data in n0's memory.

The revised claim, with evidence, is in `05-explain-execution.md` §4.
