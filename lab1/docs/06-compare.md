# Part 6 – Compare across groups

## Class table

Our rows are measured (`04-build-and-test.md`). The rows for A, B and C are
**our expectations** until the other groups report; replace them with the
class results in the session.

| strategy | scenario | predicted (valid / available) | observed |
|---|---|---|---|
| **D** | no faults | valid / yes | **valid** ×3 / all complete |
| **D** | latency 50, rate 50 | valid / yes, slower | **valid** ×3 / all complete |
| **D** | n0 crashes | valid / **no** | **valid** ×3 / nothing completes after 5 s |
| **D** | n1 crashes | valid / n1's clients no | **valid** ×3 / n1's clients only fail |
| **D** | partitions | valid / partly | **valid** ×3 / only clients of servers cut off from n0 stop |
| **D** | latency 100, rate 100 (extra) | valid / yes | **valid** ×3 / all complete |
| A | no faults | invalid (likely under load) / yes | *other group* |
| A | any crash | invalid / yes, except crashed node's clients | *other group* |
| A | partitions | invalid / yes | *other group* |
| B | no faults | valid often, invalid possible (concurrent writes at different servers ordered differently; reads at a server before its update arrives) / yes | *other group* |
| B | any crash | — / **no writes** anywhere after the crash (waits forever for the crashed node's ack) | *other group* |
| C | no faults | invalid possible (stale reads at backups) / yes | *other group* |
| C | n0 crashes | — / reads yes, writes **no** | *other group* |

## 1. Is any strategy correct in every scenario? Available in every scenario? Both?

- **Correct in every scenario: D** (in our runs, and by argument: one copy,
  executed in one order, read only there — `theory.md` §6). Every strategy
  that answers from a copy that may lack acknowledged updates (A, C, and B
  in some interleavings) can return stale values.
- **Available in every scenario: A** comes closest: each server answers its
  own clients from its own copy, whatever happens to the others. (Only the
  crashed server's own clients lose service, which no strategy can avoid
  without clients switching servers.)
- **Both: none.** This is the CAP trade-off made concrete (`theory.md` §7):
  in a partition, a server cut off from the others must either answer
  (possibly wrongly — A) or not answer (D). A single-copy design (D) gets
  correctness by having one point of failure; a no-coordination design (A)
  gets availability by giving up correctness.

## 2. B waits for every server. What does that buy, and what does it cost when a server crashes?

**Buys:** when a client gets `write_ok`, *every* copy already holds the
value, so a later read at any server sees it — the "read after acknowledged
write" rule of our specification holds for writes that do not race. (It is
still not enough for full linearizability: (i) two concurrent writes at
different servers can be applied in different orders at different copies,
so the copies diverge; (ii) while a write is in progress, a read at the
server that executed it already returns the new value, and a read that
starts *after* that one, at a server the update has not reached yet,
returns the old value — the "no going back" rule is broken even though
the write was never acknowledged.)

**Costs:** latency (the slowest server sets the pace), and **availability:
one crashed server blocks every write and cas everywhere**, because the
acknowledgement from it never comes. With N servers, B tolerates zero
crashes for writes: *worse* than one server, since now any of N can block
it.

## 3. C and D use a primary. What happens when it crashes, and how could another server take over safely?

**What happens:** in D, nothing completes anywhere (observed: 0 `ok` after
5 s in all three runs). In C, reads continue at the backups (from copies that
are frozen at whatever updates arrived) and writes stop.

**Taking over safely** needs to solve two problems.

1. **The new primary must have every acknowledged write.** In D (and C) n0
   replies *without waiting* for backups, so a write can be acknowledged and
   lost with n0. And because there are no sequence numbers and Maelstrom can
   reorder messages, a backup can even hold an *older* value than one it
   received earlier. So with our D as is, no backup is a safe successor. Fix:
   n0 replies only after a backup (or a majority) has stored the update, and
   updates carry sequence numbers so they are applied in order.
2. **There must never be two primaries at once.** A backup cannot know that
   n0 crashed — it may only be slow, or partitioned away (asynchrony,
   `theory.md` §5). If n1 promotes itself while n0 is alive, both accept
   writes and order them differently (split brain). Fix: the replicas
   **agree** on the new primary, e.g. a majority must vote for it, and each
   primary has a number (view / epoch / term); messages from an older
   primary are rejected. An old primary that cannot reach a majority must
   stop answering.

This is what Viewstamped Replication and Raft do.

## 4. Is there a middle ground between waiting for one server and waiting for all of them?

Yes: **wait for a majority (quorum)**. With N = 2f + 1 servers, wait for
f + 1 acknowledgements. Any two majorities share at least one server, so
any later operation that also contacts a majority meets someone who saw the
earlier write. The service then tolerates f crashed (or unreachable)
servers and keeps working, instead of 0 (B) or no guarantee at all (A).
With 3 servers: wait for 2, tolerate 1 crash. Majority quorums are the
basis of ABD registers and of consensus protocols (Paxos, Raft). More
generally, read quorum R and write quorum W with R + W > N.

Majorities still cannot escape CAP: in a partition, the minority side
cannot form a quorum and must stop answering.
