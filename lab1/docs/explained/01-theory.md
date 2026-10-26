# 1 · The theory, from zero

This is the theory you need to understand Lab 1 and to defend it in the
final discussion. It starts from the basics and builds up to *why* strategy D
behaves exactly as it did in our runs. The shorter summary is
`../theory.md`; this file explains the same ideas more slowly, with
examples.

Contents

1. What a "distributed system" means in this lab
2. The service we build: a key-value store
3. Histories: what we can observe
4. Linearizability: what "correct" means
5. ok, fail and info: what a client can know
6. Safety vs liveness = correctness vs availability
7. Failure models and timing models
8. Replication: the design space
9. Strategy D: primary-backup without failover
10. CAP: why no strategy gets everything
11. Beyond Lab 1: failover, quorums, consensus
12. Glossary

---

## 1. What a "distributed system" means in this lab

A distributed system is a set of **processes** that cooperate **only by
sending messages**. In this lab:

- each **server** (`n0`, `n1`, `n2`) is a separate operating-system process
  running our Python program (`d.py`);
- **clients** (`c6`, `c7`, …) are simulated by Maelstrom;
- they share **no memory** and **no clock**. The only way for n1 to learn
  something about n0 is to receive a message from it.

Three facts make this hard, and every topic below follows from them:

1. **Messages take time**, and you don't know how long. A message may arrive
   after 1 ms or after 500 ms. It may overtake a message sent earlier
   (*reordering*).
2. **Messages can be lost**, for example when the network is partitioned or
   the receiver has crashed.
3. **Processes can fail**, and the others cannot see it happen. They can
   only notice that no message has arrived for a while, and that looks
   exactly the same as "slow".

---

## 2. The service we build: a key-value store

The `lin-kv` workload asks for a map `key → value` (both integers) with
three operations:

| operation | what it does | normal reply | error replies |
|---|---|---|---|
| `read(k)` | returns the current value of `k` | `read_ok` with `value` | 20 if `k` was never written |
| `write(k, v)` | sets `k` to `v` | `write_ok` | none |
| `cas(k, a, b)` | **c**ompare-**a**nd-**s**et: if `k` holds `a`, set it to `b` | `cas_ok` | 20 if `k` does not exist, 22 if it holds something other than `a` |

Each key is independent of the others and behaves like a **register**: one
memory cell that you can read, write and compare-and-set.

### The sequential specification

The table above is the **sequential specification**. It says what the
answers must be *if operations happen one after another, on one copy*.
Example for key `x`:

```
write(x, 1)    → write_ok          x = 1
read(x)        → read_ok 1
cas(x, 1, 3)   → cas_ok            x = 3
cas(x, 1, 4)   → error 22          x still 3 (it was not 1)
read(x)        → read_ok 3
```

This part is easy. The whole lab is about the hard question: **what is
"correct" when operations do *not* happen one after another?** That happens
when there are several clients at the same time, several servers, and
failures.

### Why cas matters

`cas` is what makes this a useful store: it lets clients build counters,
locks and similar things without losing updates ("increment if nobody
changed it meanwhile"). It is also the operation that copies get wrong most
easily. If two copies both hold `1` and two clients send `cas(x, 1, …)` to
different copies, **both succeed**. On one real register only one of them
could have.

### Error codes (Maelstrom's convention)

| code | name | meaning for the checker |
|---|---|---|
| 11 | temporarily unavailable | the operation **definitely did not happen** |
| 13 | crash | the operation **may or may not** have happened |
| 20 | key does not exist | definite: nothing happened |
| 22 | precondition failed (cas mismatch) | definite: nothing happened |

Remember 11 vs 13. A server may answer 11 **only if it is sure** the
operation had no effect. Section 5 shows why that is rarely true.

---

## 3. Histories: what we can observe

We cannot see "inside" a distributed system. What we *can* record is, for
every client operation:

- its **invocation**: the moment the client sends the request;
- its **completion**: the moment the client gets the answer, and what the
  answer was.

The list of all invocations and completions is a **history**. Maelstrom
writes it to `history.txt` / `history.edn`. Every operation becomes an
**interval** on a time line:

```
time ───────────────────────────────────────────────►

p0:   [──── write(x,1) ────]
p1:          [────── read(x) → ? ──────]
p2:                                [── read(x) → ? ──]
```

Two operations are **concurrent** if their intervals overlap (p0 and p1
above). If one finishes before the other starts, they are in **real-time
order** (p0's write finished before p2's read started: write → read).

---

## 4. Linearizability: what "correct" means

### The definition

A history is **linearizable** if you can choose, for every operation, one
instant (its **linearization point**) such that:

1. the instant lies **inside** the operation's interval (after the
   invocation, before the completion), and
2. if you execute all the operations one at a time in the order of those
   instants, using the sequential specification, you get **exactly the
   answers the clients got**.

In plain words: *the system behaves as if there were a single copy and every
operation happened instantly at some moment while the client was waiting.*
Clients cannot tell it apart from one perfect server.

### Example 1: concurrent read, two legal answers

```
x = 0 initially

p0:   [──────── write(x,1) ────────]
p1:        [── read(x) → 0 ──]
```

Put p1's point before p0's point: the read sees 0. **Legal.**

```
p0:   [──────── write(x,1) ────────]
p1:        [── read(x) → 1 ──]
```

Put p0's point first: the read sees 1. **Also legal.**

So **a read concurrent with a write may return either the old or the new
value.** (Part 1 of the guide asks exactly this.)

### Example 2: a stale read, illegal

```
p0:   [─ write(x,1) ─]
p1:                       [─ read(x) → 0 ─]
```

The write *finished* before the read *started*. Every choice of points puts
the write before the read, so the read must see 1. It returned 0, so no order
explains it: **not linearizable**. This is a **stale read**.

So **a read that starts after a write was acknowledged must return that
value or a newer one.**

### Example 3: "no going back"

```
p0:   [──────────── write(x,1) ────────────]
p1:      [─ read → 1 ─]
p2:                       [─ read → 0 ─]
```

Each read on its own overlaps the write, so each could be fine. But p1 has
already seen 1, so the write's point is before p1's point, and p2's read
starts after p1's read ended. So p2's point is after the write too, and p2
must see 1. **Not linearizable.** Once anyone has seen the new value, nobody
who starts later may see the old one, even while the write is still in
progress.

### Example 4: our real anomaly (Part 2, three independent `kv.py`)

From `runs/p2-independent` (key 0):

```
p5  write(0,0) at n2 → ok          n2's dict: 0
p3  write(0,2) at n0 → ok          n0's dict: 2      (finished at 3.066 s)
p0  read(0)    at n0 → 2           (3.104–3.106 s)
p2  read(0)    at n2 → 0           (starts 3.256 s, after both of the above)
```

p2's read started after `write(0,2)` was acknowledged **and** after p0 had
read 2. It must return 2, but it returned 0, because n2 has its own
dictionary and never heard of the write. Maelstrom's `linear.svg` says
*"can't read 0 from register 2"*: at that point in any legal order the
register holds 2.

### Why the checker looks at each key separately

Linearizability is **local** (also called *composable*): a store is
linearizable if and only if each key, taken on its own, is linearizable.
So Maelstrom splits the history by key and checks each one
(`store/…/independent/<key>/`). That is much cheaper than checking
everything together.

### How the checker works (Knossos)

Maelstrom uses the **Knossos** checker with a `CASRegister` model. It
searches through the possible orders of operations (respecting real time)
and simulates the register for each order. If at least one order explains
every answer, the result is `:valid? true`. If none does, it reports the
smallest contradiction it found and draws it in `linear.svg`. The search is
exponential in the worst case, which is one reason the tests are short
(20 s) and use few keys.

### Linearizability vs weaker models

| model | what it promises | example of an allowed "surprise" |
|---|---|---|
| **linearizable** | single copy, real-time order respected | none |
| sequential consistency | one global order, consistent with each client's own order, but **not** with real time | you write, then *someone else* reads the old value afterwards |
| causal consistency | operations that are causally related are seen in order by everyone | two concurrent writes seen in different orders by different clients |
| eventual consistency | if writes stop, copies eventually agree | anything stale, for any time |

The lab uses the strongest model, linearizability. Any stale read is a bug.

---

## 5. ok, fail and info: what a client can know

### The core problem (Part 0, question 1)

A client sends `write(x, 5)`. The server crashes at some moment. What can
happen?

| crash happens… | was x set to 5? | what the client sees |
|---|---|---|
| before the request arrives | no | nothing |
| after arrival, before executing | no | nothing |
| after executing, before replying | **yes** | nothing |
| after replying, but the reply is lost | **yes** | nothing |
| (no crash, the server or network is just slow) | not *yet* | nothing… for now |
| after the reply arrived | yes | `write_ok` |

**The client sees only two things: `write_ok`, or nothing.** "Nothing" mixes
"done", "not done" and "not yet". No timeout length can separate them,
because a message can always be slower than your timeout. This is the
**fundamental uncertainty** of asynchronous systems.

### The three outcomes in a history

| outcome | meaning | how the checker treats it |
|---|---|---|
| **ok** | it happened, with this result | must be placed in the linear order |
| **fail** | it **definitely did not happen** (error 20, 22, 11) | removed from the history |
| **info** | **unknown** (timeout or error 13) | *may* be placed anywhere after its invocation, *or* left out |

Two consequences explain many of our numbers:

1. **An info can never make a history invalid on its own.** The checker can
   always place it where it fits, or drop it. So a server that never answers
   is never "wrong", only unavailable.
2. **A timed-out *read* is recorded as fail, not info.** A read changes
   nothing, so treating it as "did not happen" is always safe. In our crash
   runs the `fail` count therefore includes timed-out reads, and only
   timed-out writes and cas operations become `info`.

### Process retirement

Maelstrom's checker assumes each client process does **one operation at a
time**. After an `info`, the process's last operation might still take
effect at any future time, so the process cannot safely issue another one.
Maelstrom **retires** it and starts a new process number on the same node
(p1 → p3 → p5 …). That is why process numbers keep growing in crash runs.

### Info writes really can have taken effect

In `runs/p4-partition-2`, n1 forwarded `write(0,3)` to n0. n0 executed it,
but n0's reply to n1 was dropped by the partition, so the client recorded
`info`. Meanwhile another client read `3` from n0. The checker *had to*
place the info write before that read, and it could, so the run was valid.
**An info is not "failed". It is "unknown".**

### Why error 11 would have been a lie in D

Suppose a backup gave up waiting for n0 and answered "11, temporarily
unavailable". 11 means "surely not done". But n0 might have executed the
request and only the reply was lost (exactly the case above). The checker
would then remove an operation that *did* happen, and another client could
observe its value with no write to explain it: **invalid**. The honest
answer after a timeout is 13 ("maybe"), or no answer at all. D gives no
answer.

---

## 6. Safety vs liveness = correctness vs availability

Two kinds of properties:

- **Safety**: "nothing bad ever happens". Here: no answer contradicts
  linearizability. A safety violation is visible at a specific moment (a
  stale read at 3.257 s).
- **Liveness**: "something good eventually happens". Here: requests
  eventually get an answer. A liveness violation is never visible at one
  point, only as "still waiting…".

In this lab:

| | property | Maelstrom reports it as |
|---|---|---|
| **correctness** | safety | `:valid?` (and `linear.svg` if false) |
| **availability** | liveness | `:ok-count`, `:info-count`, `:availability {:ok-fraction …}` |

**They are independent.** A server that never answers is perfectly correct
and totally unavailable. A server that always answers from its own possibly
stale copy is perfectly available and possibly incorrect. The point of the
lab is to see that naive replication buys one at the price of the other.

---

## 7. Failure models and timing models

### What can fail, and how

| model | behaviour | in the lab |
|---|---|---|
| **crash-stop** | process stops forever, does nothing afterwards | `MS_CRASH="n0@5"` |
| **crash-recover (memory kept)** | stops, later resumes with its state; messages sent meanwhile are lost | `MS_CRASH="n0@5-12"` (our `pause-n0`) |
| **crash-recover (amnesia)** | restarts with empty or old state | *not injectable in this kit* |
| **omission** | some messages are lost | partitions; messages to a crashed node |
| **network partition** | nodes split into groups that cannot talk; may be **asymmetric** (A hears B but B doesn't hear A) | `--nemesis partition` |
| **Byzantine** | arbitrary or malicious behaviour | not in this course |

Note: `MS_CRASH` is implemented by `ms.py`, not by Maelstrom. The process
keeps running but drops everything (see `03-ms-py.md`). For everyone else,
it simply goes silent, which is what a real crash looks like from outside.

### Timing

- **Synchronous**: there are *known* upper bounds on message delay and
  processing time. A timeout then reliably means "crashed".
- **Asynchronous**: no bounds at all. "Crashed" and "slow" are
  **indistinguishable**. Failure detectors are unreliable.
- **Partially synchronous**: bounds exist but are unknown, or hold only
  eventually. This is the realistic model that real protocols (Raft, Paxos)
  are designed for: always safe, live when the network behaves.

We assume **asynchrony** for correctness. That is why D never trusts a
timeout to decide anything: it has no timeouts at all.

A famous consequence (the FLP result, Fischer–Lynch–Paterson 1985): in a
purely asynchronous system with even one crash, no deterministic protocol
can guarantee that replicas always reach agreement *and* always terminate.
Real systems guarantee safety always and liveness only "when things calm
down".

---

## 8. Replication: the design space

Replication means keeping several copies (**replicas**) of the state so the
service survives the loss of some of them. Every replication protocol
answers four questions:

1. **Who executes a request?** Any replica, or one **primary**?
2. **What is sent to the others?** The *operation* ("do write(x,5)"), which
   requires every replica to execute the same operations in the same order,
   or the *resulting state* ("x is now 5"), which needs no re-execution.
3. **When does the client get its reply?** Before propagating, after *all*
   replicas acknowledge, or after *some* (a quorum)?
4. **Who answers reads?** Any replica (fast, maybe stale), or only the one
   that orders writes?

The four strategies of the lab:

| | who executes | when the reply is sent | who answers reads | expected problem |
|---|---|---|---|---|
| **A** update, reply, propagate | receiver | before propagating | receiver | stale reads; diverging copies; double cas success |
| **B** update, propagate, wait for all | receiver | after **all** ack | receiver | concurrent writes ordered differently; one crash blocks all writes |
| **C** primary for writes | n0 (writes/cas) | n0, no waiting | **any** replica, own copy | stale reads at backups |
| **D** primary for everything | n0 (all) | n0, no waiting | **n0 only** | n0 is a single point of failure |

### Mini-scenarios showing each problem

**A, stale read:** client writes `x=5` at n1. n1 replies ok and *then*
sends the update. Another client reads at n2 before the update arrives and
gets the old value, after the write was acknowledged. Invalid.

**A/B, divergence:** at the same time, n1 executes `write(x,1)` and n2
executes `write(x,2)`. Each sends its update to the other. n1 ends with 2,
n2 ends with 1. The copies disagree forever.

**B, blocking:** n2 crashes. n1 executes a write and waits for n2's
acknowledgement, which never comes. No write completes anywhere.

**C, stale read:** a write goes to n0, is executed and acknowledged. A read
at n2 arrives before n0's update reaches n2, so n2 answers from its old
copy. Invalid.

**D:** none of the above, because the backups' copies are never read. The
price is that everything depends on n0. Section 9 explains why.

---

## 9. Strategy D: primary-backup without failover

> *Every request is forwarded to n0, which executes it and sends the update
> to the others.*

This is a form of **primary-backup** (also called *passive replication*):
one replica, the **primary**, orders and executes everything, and the
**backups** receive the results.

### Why D is always linearizable (proof sketch)

Take any operation `op` that a client completed with `ok` (or a definite
`fail`):

1. Its answer was produced by n0, because only `execute()` (which runs only
   on n0) generates answers. Backups only relay them.
2. n0 runs `execute()` for one message at a time (`ms.py` has a single
   worker thread), and each `execute()` reads or updates the dict and
   decides the answer in one uninterrupted step. Call that instant `t(op)`.
3. `t(op)` is **after the invocation**: the request had to travel
   client → (backup →) n0 first.
4. `t(op)` is **before the completion**: the answer is sent only after
   execution and has to travel back.
5. The order of the `t(op)` instants is the order in which n0 executed the
   operations on **one** dict. So each answer is exactly what the
   sequential specification gives in that order.

Conditions 1 and 2 of the definition are met, so the history is
linearizable. **`t(op)` is the linearization point.** In our traces it is
the `execute` event.

For `info` operations: either n0 executed them (point = that instant, still
inside "after invocation") or it did not (leave them out). Both are allowed.

### What faults can and cannot do to D

Faults **remove** messages or **delay** them. They never **change** an
answer:

- a lost request → n0 never executes it → client gets nothing → `info` / `fail`;
- a lost reply → n0 executed it → client gets nothing → `info` (but it happened);
- a delay → the linearization point moves, but it stays inside the interval;
- a crashed backup → its clients get nothing; nobody else notices;
- a crashed n0 → nobody gets anything.

**None of these produces a wrong answer, so D is always valid.** That
matches our 19/19 valid runs. It is a structural property, not luck.

### The hidden flaw: backups silently diverge

n0 sends updates *fire and forget*: no acknowledgement, no retry, no
sequence number. So a backup's copy can be:

- **missing updates** (it was crashed or partitioned when they were sent);
- **out of order**: Maelstrom may reorder messages, so `update(x,1)` sent
  before `update(x,2)` can arrive after it, and the backup ends with
  `x = 1` while n0 has `x = 2`.

In `runs/p4-partition` the run ended with n2 holding 4 and n0 holding 3.
**Under D nobody ever reads a backup, so this is invisible.** It becomes a
problem the moment anyone wants a backup to take over (section 11).

### Availability of D

D is exactly as available as n0:

| situation | clients of n0 | clients of a backup |
|---|---|---|
| no faults | ✔ | ✔ (slower: two extra hops) |
| backup crashed | ✔ | its own clients ✘, the other backup's ✔ |
| n0 crashed | ✘ | ✘ |
| backup partitioned from n0 | ✔ | ✘ while cut off |

**D is a single server with extra hops.** It solved the consistency problem
of three independent servers by having only *one copy that matters*. That
also means it kept the single server's single point of failure. The two
backups add no fault tolerance at all.

---

## 10. CAP: why no strategy gets everything

The **CAP theorem** (Brewer's conjecture, proved by Gilbert & Lynch, 2002):
when the network is **P**artitioned, a replicated service cannot provide
both **C**onsistency (linearizability) and **A**vailability (every request
to a non-failed server gets an answer).

Intuition: n2 is cut off from n0. A client asks n2 to read `x`. n2 can:

- **answer** from its own copy. That is available, but n0 may have accepted
  newer writes, so the answer may be stale and not consistent (this is what
  A and C do);
- **refuse or wait**. That is consistent, but this client gets nothing, so
  it is not available (this is what D does).

There is no third option. In this lab:

- D chose **C** (consistency): observed as `valid` + `info` for cut-off clients.
- A (and C, for reads) choose **A** (availability): expected invalid runs.

This is the answer to Part 6, Q1: **no strategy is both correct and
available in every scenario, and none can be.**

---

## 11. Beyond Lab 1: failover, quorums, consensus

### Safe failover (Part 6, Q3)

To survive n0 crashing, a backup must take over. Doing that safely needs
two things that D lacks:

1. **The new primary must have every acknowledged write.** In D, n0 replies
   without waiting, so an acknowledged write may exist only in n0's memory.
   *Fix:* n0 replies only after enough backups have **stored** the update
   (acknowledged it). Updates carry **sequence numbers** so backups apply
   them in order and can detect gaps.
2. **There must never be two primaries at once (no split brain).** A backup
   can't know that n0 crashed. n0 may be slow or on the other side of a
   partition, still serving its own clients. If n1 promotes itself, two
   primaries accept writes in different orders, which is invalid.
   *Fix:* the replicas **agree** on the new primary (for example, a
   majority votes), and every primary has a number (**view / epoch /
   term**). Messages from an older number are rejected. A primary that
   cannot reach a majority must stop answering.

### Quorums (Part 6, Q4)

The middle ground between "wait for one" (A, C, D) and "wait for all" (B)
is **wait for a majority**.

- With N replicas, a majority is ⌊N/2⌋ + 1. For N = 3 that is 2.
- **Any two majorities overlap** in at least one replica: 2 + 2 > 3. So a
  later operation that contacts a majority always reaches *someone* who saw
  the earlier write.
- With N = 2f + 1 replicas, the system keeps working with up to **f**
  replicas crashed or unreachable. For N = 3, f = 1.
- In general: a read quorum R and a write quorum W with **R + W > N**
  guarantee that they intersect.

| wait for | tolerates crashes (N=3) | consistency |
|---|---|---|
| 1 (A, C) | 2 for availability | none guaranteed |
| all 3 (B) | **0** for writes | better, still not linearizable |
| majority 2 | 1 | can be made linearizable (ABD, Raft) |

### Consensus

Majority quorums + an agreed leader with a term number + an ordered **log**
of operations = **consensus / state-machine replication**: Paxos,
Viewstamped Replication, Raft (Maelstrom's `doc/06-raft/` builds one). Such
a system is linearizable and stays available as long as a majority is up
and connected. On the **minority** side of a partition it must still stop
answering. CAP still applies; consensus just picks the best possible
point.

---

## 12. Glossary

| term | meaning |
|---|---|
| **node / server / replica** | one of our processes n0, n1, n2 |
| **primary** | the replica that executes and orders operations (n0 in D) |
| **backup** | a replica that only receives updates (n1, n2 in D) |
| **client id** (`c6`) | network name of a simulated client; appears in `msg.src` |
| **process** (`p3`) | logical client in the history; one operation at a time |
| **invocation / completion** | start and end of an operation, seen by the client |
| **history** | the list of all invocations and completions |
| **concurrent** | two operations whose intervals overlap |
| **linearization point** | instant at which an operation "takes effect" |
| **linearizable** | there are linearization points that explain every answer |
| **stale read** | a read returning a value older than an acknowledged write |
| **ok / fail / info** | happened / definitely not / unknown |
| **safety / liveness** | nothing bad happens / something good eventually happens |
| **availability** | fraction of requests that get an answer (`:ok-fraction`) |
| **crash-stop / crash-recover** | stops forever / stops and comes back |
| **partition** | servers cannot exchange messages; may be asymmetric |
| **asynchronous** | no bound on delays; crashed and slow look the same |
| **fire and forget** | send without waiting for, or checking, an answer |
| **state transfer** | send the new value, not the operation |
| **split brain** | two replicas both acting as primary |
| **quorum** | a subset of replicas big enough that any two subsets overlap |
| **nemesis** | Maelstrom's fault injector (here: partitions) |
| **Knossos** | the linearizability checker Maelstrom uses |
