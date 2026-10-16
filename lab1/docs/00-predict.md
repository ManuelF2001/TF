# Part 0 – Predict

> The lab asks for these answers **individually, without discussion and
> without AI**. What follows are reference answers, written afterwards. Each
> member should still keep their own original answers and compare: the
> differences are useful for the final discussion. The answers are revisited
> at the end of `05-explain-execution.md`.

## 1. `write(x, 5)` to a single server that crashes at some moment

Possible outcomes, depending on when the crash happens:

| crash happens … | state of `x` | what the client sees |
|---|---|---|
| before the request arrives | unchanged | no reply (timeout) |
| after arrival, before executing | unchanged | no reply (timeout) |
| after executing, before replying | `x = 5` | no reply (timeout) |
| after replying, but the reply is lost/delayed | `x = 5` | no reply (timeout) |
| after the reply arrives | `x = 5` | `write_ok` |

(If the server keeps its state only in memory, after the crash `x` is
unreachable anyway: "happened" means "happened before the crash".)

**Can the client always tell which one happened? No.** It sees only two
things: `write_ok`, or nothing. "Nothing" covers both "done" and "not done",
and also "not yet, the server or network is just slow". In an asynchronous
system no timeout length separates these cases. Only `write_ok` is
conclusive. This is exactly what Maelstrom records as `info` (outcome unknown).

## 2. "The key-value store works correctly if …"

… every operation appears to take effect **instantaneously at some point
between its invocation and its response**, and the results are those of
executing the operations one at a time in that order on a single copy: a
read returns the value of the latest write (or successful cas) before it,
a cas succeeds exactly when the current value equals `from`. In particular a
read that starts after a write was acknowledged returns that value or a
newer one. (This is **linearizability**, see `theory.md` §2.)

Not part of "correct": that every request gets an answer. That is
availability (`theory.md` §4).

## 3. Three copies of the server

**What goes away:** with three copies the data and the service can survive
one server's crash — if another copy has the write, it is not lost, and a
client can be served by another server.

**What does not go away:** the client still cannot tell whether a write
whose reply never came took effect. Indeterminacy is a property of the
client–server exchange, not of the number of copies.

**What appears:**

- the copies can **disagree** (an update has reached some but not others),
  so different clients can read different values — stale reads;
- concurrent writes at different servers can be applied in **different
  orders** at different copies, so the copies diverge permanently;
- a `cas` checked against one copy may be wrong for another (two clients
  both succeed in `cas(x, 1, …)`);
- deciding **when to reply** (after one copy? all? some?) and what to do when
  a copy is down or unreachable;
- **partitions**: servers that are up but cannot talk to each other;
- **failure detection**: a server cannot tell whether another one crashed or
  is slow, so "taking over" from a crashed server can lead to two servers
  thinking they are in charge.

In short: replication trades the single point of failure for the problem of
keeping copies consistent.
