# Theory behind Lab 1

This file collects the concepts the lab relies on. The other documents refer
to its sections.

---

## 1. The service: a key-value store of registers

The `lin-kv` workload is a map from integer keys to integer values with three
operations:

| operation | effect on key `k` | reply |
|---|---|---|
| `read(k)` | none | `read_ok(v)` with the current value, or error 20 if `k` was never written |
| `write(k, v)` | value becomes `v` | `write_ok` |
| `cas(k, a, b)` | if value is `a`, it becomes `b` | `cas_ok`; error 22 if the value is not `a`; error 20 if `k` does not exist |

Each key behaves as an independent **compare-and-set register**. The
**sequential specification** is this table: what happens if operations run one
after the other on a single copy. The difficulty is saying what is correct
when they do *not* run one after the other: several clients, concurrent
requests, several servers, failures.

## 2. Linearizability (the checker's notion of correctness)

A history (the record of every invocation and response) is **linearizable**
if we can pick, for every operation, a single instant — its *linearization
point* — such that:

1. the point lies between the operation's invocation and its response;
2. executing the operations one at a time in the order of their points, using
   the sequential specification, gives exactly the responses the clients got.

Consequences, which answer the questions of Part 1:

- **Real-time order is respected.** If operation A's response arrives before
  operation B is invoked, A's point is before B's. So a `read` that *starts
  after* `write(k, v)` was acknowledged must return `v` or a value written
  later — never an older one. Reading an older value is a **stale read**.
- **Concurrent operations may be ordered either way.** A `read` that overlaps a
  `write(k, v)` may return the old value or `v`. But once one client has seen
  `v`, any read that starts after that must not return the old value (no
  "going back in time").
- **It is composable:** a store is linearizable iff each key is. That is why
  Maelstrom checks each key separately (`store/.../independent/<key>/`).

Linearizability makes a replicated store indistinguishable from a single
server that executes requests one at a time. Weaker models (sequential
consistency, causal consistency, eventual consistency) drop some of these
guarantees; the lab uses the strong one.

### How Maelstrom checks it

Maelstrom uses the Knossos checker with a `CASRegister` model. It searches
for an order of the operations that satisfies the two rules above. When none
exists it reports `:valid? false` and draws a minimal counterexample in
`linear.svg` (e.g. *"can't read 0 from register 2"*: the model's register
holds 2 at that point, and no legal order lets the read return 0).

## 3. ok, fail and info: what the client knows

Every operation in the history ends in one of three ways:

| outcome | meaning | how the checker uses it |
|---|---|---|
| `ok` | the operation happened, with this result | must be linearized |
| `fail` | the operation **definitely did not happen** (e.g. error 20 or 22, or error 11) | removed from the history |
| `info` | **unknown**: no answer arrived (timeout), or error 13 "crash" | may be linearized at any point after its invocation, *or not at all* |

`info` is the honest answer when a client gets no reply. In an
**asynchronous** system a client cannot distinguish:

- the request was lost before reaching the server;
- the server crashed before executing it;
- the server executed it and crashed before replying;
- the server executed it and the reply was lost;
- the server (or network) is just slow.

The first two mean "not done", the next two mean "done", the last means "not
yet". This is the heart of Part 0, question 1: **a timeout does not tell you
whether the operation took effect.**

Since an `info` operation can always be placed "at the end" or dropped, it can
never make a history non-linearizable on its own. That is why a server that
stops answering is still *correct* — it is just not *available*.

> Note on error codes: replying error 11 ("temporarily unavailable") tells the
> checker the operation *surely did not happen*. A server may only use it when
> that is true. Error 13 ("crash") means "may or may not have happened" and is
> treated like `info`.

## 4. Correctness (safety) vs availability (liveness)

- **Safety / correctness:** nothing bad happens — every response is consistent
  with the specification (here: the history is linearizable).
- **Liveness / availability:** something good eventually happens — requests
  get (`ok` or definite `fail`) answers.

They are independent: a server that never replies is perfectly safe and
totally unavailable; a server that always replies from a local, possibly
stale copy is available and possibly wrong. Maelstrom reports both: the
verdict (`:valid?`) for safety, and `:ok-count / :fail-count / :info-count`
and `:availability {:ok-fraction ...}` for availability.

## 5. Fault and timing models

| model | what it means | in the lab |
|---|---|---|
| **crash-stop** | a process stops forever and does nothing afterwards | `MS_CRASH="n0@5"` |
| **crash-recover / pause** | a process stops and later resumes (here with its memory intact; messages sent to it meanwhile are lost) | `MS_CRASH="n1@5-12"` |
| **omission** | messages are lost | messages to/from a crashed node; partitions |
| **network partition** | the nodes are split into groups that cannot exchange messages, for a while | `--nemesis partition` |
| **Byzantine** | arbitrary behaviour (lying, corruption) | not used |

Timing:

- **synchronous**: known bounds on message delay and processing time → a
  timeout reliably detects a crash;
- **asynchronous**: no bounds → a timeout can never distinguish "crashed"
  from "slow"; failure detection is unreliable;
- **partially synchronous**: bounds exist but are unknown, or only hold
  eventually. Real systems are designed for this.

Maelstrom's network adds random delay (`--latency`) and may reorder messages;
our nodes must not assume FIFO delivery between two nodes.

## 6. Replication: what can be copied, and when to answer

A replicated service keeps several copies (**replicas**) of the state so that
the service survives the loss of some of them. The design choices are:

- **who executes** a request: any replica (multi-leader / active), or one
  **primary** that orders everything (primary-backup / passive replication);
- **what is sent** to the others: the operation (operation transfer, needs
  deterministic execution in the same order everywhere) or the resulting
  state (state transfer);
- **when to reply** to the client: before propagating (fast, but the update
  can be lost or not yet visible elsewhere), after *some* replicas acknowledge,
  or after *all* do (strong, but one slow or crashed replica blocks everyone);
- **who may answer reads**: any replica (fast, maybe stale) or only the one
  that orders writes.

The four strategies of the lab are points in this space:

| | executes | replies | reads served by |
|---|---|---|---|
| A | receiver | before propagating | receiver |
| B | receiver | after **all** acks | receiver |
| C | primary for writes | primary, without waiting for acks | **any** replica |
| D | primary for everything | primary, without waiting for acks | **primary only** |

### Why D is linearizable while the primary is up

In D every operation is executed by a single thread at n0, one at a time, on
one copy. The linearization point of each operation is the instant n0
executes it, and that instant lies between the client's invocation (the
request has to reach n0 first) and the client's response (the reply can only
be sent after execution). The backups' copies are never read, so their
staleness or disorder cannot be observed. D is, in effect, **a single server
with extra hops** — and therefore inherits the single server's weakness:
when n0 stops, nobody can answer.

## 7. The CAP trade-off

During a network partition a replicated service must choose: keep answering
on both sides (**availability**) and risk inconsistent answers, or refuse on
the side that cannot reach the authority (**consistency**). It cannot have
both (Gilbert & Lynch's formalization of Brewer's conjecture). Strategies A
and C pick availability; D picks consistency: clients whose server is cut off
from n0 get no answer.

## 8. Beyond this lab: failover, quorums, consensus

These are the answers to Part 6 and the subject of later labs.

- **Failover.** To survive a primary crash another replica must take over.
  Doing it safely requires (1) the new primary has every acknowledged update
  — so the old primary must not reply before the update is stored on the
  replica that will take over; (2) only one primary at a time — a backup that
  merely *suspects* n0 has crashed may be wrong (asynchrony), and two
  primaries (**split brain**) would order operations differently. Mechanisms:
  numbered views/epochs/terms, sequence numbers on updates, and agreement
  among the replicas on who the primary is.
- **Quorums.** The middle ground between waiting for one replica and waiting
  for all: wait for a **majority** (⌊N/2⌋+1). Any two majorities intersect, so
  a later operation always meets at least one replica that saw the earlier
  one. With N = 2f+1 replicas the system tolerates f crashes and still
  progresses. More generally, read quorum R and write quorum W with
  R + W > N guarantee intersection.
- **Consensus.** Primary election + majority quorums + logs are what Paxos,
  Viewstamped Replication and Raft provide: a linearizable service that stays
  available as long as a majority is up and can communicate (it still
  becomes unavailable in a minority partition, as CAP requires).

## References

- M. Herlihy, J. Wing. *Linearizability: a correctness condition for
  concurrent objects*. ACM TOPLAS, 1990.
- S. Gilbert, N. Lynch. *Brewer's conjecture and the feasibility of
  consistent, available, partition-tolerant web services*. SIGACT News, 2002.
- N. Budhiraja et al. *The primary-backup approach*. In *Distributed Systems*
  (S. Mullender, ed.), 1993.
- Maelstrom documentation: `../../maelstrom/doc/` (especially
  `workloads.md` and `06-raft/`).
