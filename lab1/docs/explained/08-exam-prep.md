# 8 · Preparing for the individual discussion

The guide says: *"each member is asked individually to explain (or extend)
what the group did."* Below are the questions an examiner is most likely to
ask, with short answers and a pointer to the full explanation. Cover the
answer, try it yourself, then check.

(You can also ask an AI assistant to quiz you: `kit/AGENTS.md` has a "quiz
mode". Say "quiz me on lab 1" and point it to `record/record.tex` and
`code/d.py`.)

---

## A. Concepts

**A1. What does linearizable mean?**
Every operation appears to take effect at a single instant between its
invocation and its response, and the answers match executing the operations
one at a time in that order on a single copy. → `01-theory.md` §4

**A2. A read overlaps a write of 5 (old value 0). What may it return?**
0 or 5, both legal. But if it starts *after* the write was acknowledged, it
must return 5 (or newer). And if someone already read 5, later reads can't
return 0. → `01-theory.md` §4, examples 1–3

**A3. Difference between `fail` and `info`?**
`fail`: definitely did not happen, so the checker removes it. `info`:
unknown, so the checker may place it anywhere after its invocation, or drop
it. → `01-theory.md` §5

**A4. Why is a timed-out read a `fail` and a timed-out write an `info`?**
A read has no effect, so "did not happen" is always a safe assumption. A
write might have happened. → `01-theory.md` §5

**A5. Why can't the client know whether its write happened, after a
timeout?**
"No reply" is the same for lost request, crash before executing, crash
after executing, lost reply, and slow. In an asynchronous system no timeout
separates them. → `01-theory.md` §5; observed in `runs/p4-partition-2`

**A6. Correctness vs availability?**
Safety (no wrong answers, measured by `:valid?`) vs liveness (requests get
answers, measured by ok/info counts and `:ok-fraction`). They are
independent: silence is correct, while answering from a stale copy is
available but wrong. → `01-theory.md` §6

**A7. What is CAP and where did you see it?**
During a partition you can't have both linearizability and every server
answering. D chose consistency: in `runs/p4-partition`, clients of n1/n2
got no answers while n0 was cut off, and the run was valid.
→ `01-theory.md` §10

**A8. Synchronous vs asynchronous system?**
Known bounds on delays vs no bounds. In asynchronous systems, crashed and
slow are indistinguishable, so timeouts can't be trusted to detect crashes.
→ `01-theory.md` §7

**A9. Why does Maelstrom check each key separately?**
Linearizability is local/composable: the whole store is linearizable iff
each key is. Checking per key is much cheaper. → `01-theory.md` §4

---

## B. Our design

**B1. State strategy D in one sentence.**
Every request (read, write, cas) is forwarded to the fixed primary n0,
which executes it, sends the new value to the backups without waiting, and
replies; the receiving backup relays the reply.

**B2. Which details did you have to decide, and what did you choose?**
Send the new value, not the operation. Backups overwrite on arrival, with
no ack and no ordering. cas runs only at n0. Backups never answer from
their copy and have no timeout. No failover. → `05-d-py.md` lines 3–19

**B3. Why is D always linearizable?**
Every answer is produced by n0's `execute()`, one at a time (single worker
thread), on one dict, between the request's arrival and the reply's
departure. That instant is the linearization point. Backups' copies are
never read. Faults only drop or delay messages, which produces no answer,
never a wrong one. → `01-theory.md` §9

**B4. Where is the linearization point in your code?**
The `execute` call on n0. In the trace it is the `execute` event
(`d.py` lines 77/80/85/92/95/100).

**B5. Why do backups forward reads too? Isn't that wasteful?**
Yes, it costs two hops. But answering reads locally is strategy C, which
allows stale reads: a backup's copy may lack an acknowledged write. The
forwarding of reads is precisely what makes D correct.

**B6. Why does n0 send the value and not the operation?**
So backups never re-evaluate a cas. With operations, backups would need the
same order as n0 to reach the same result, and there are no sequence
numbers. → `05-d-py.md` Part D, Q4

**B7. Are the backups' copies consistent with n0?**
Not necessarily. Updates can be lost (crash/partition) or reordered (no
sequence numbers). Observed: `runs/p4-partition` ends with n2 = 4, n0 = 3.
It's invisible because nobody reads them.

**B8. Then why have backups at all?**
Under D they serve no purpose for correctness or availability. They are
there so a *future* failover could use them, but as they are (no acks, no
ordering), none of them could safely take over.

**B9. What happens if two clients at n1 and n2 send `cas(x, 1, …)` at the
same time?**
Both are forwarded to n0, which executes them one after the other. The
first succeeds, and the second sees the new value and gets error 22. At most
one succeeds, as on a single register.

---

## C. The code

**C1. Why don't you need locks?**
`ms.py` runs every handler and callback on a single worker thread
(`ThreadPoolExecutor(max_workers=1)`), one at a time. → `03-ms-py.md` §3

**C2. Why can't `forward` wait for n0's answer?**
The answer can only be processed by that same thread after `forward`
returns. Waiting would deadlock the node. That's why `rpc` takes a callback
(`relay`).

**C3. What is `relay` and how does it know which client to answer?**
A closure defined inside `forward`. It remembers that call's `msg` (the
client's request), so `reply(msg, …)` goes to the right client with the
right `in_reply_to`. → `05-d-py.md` lines 59–64

**C4. How does n1 know that a message from n0 is the answer to *its*
forward?**
`rpc` stored `relay` in `_pending[msg_id]`. n0's reply carries
`in_reply_to = msg_id`. `ms.py`'s `_dispatch` pops the callback and calls
it instead of `handle`. → `03-ms-py.md` §5

**C5. Why does `forward` remove `msg_id` from the request?**
`_send` builds `sn(msg_id=mid, **body)`, and a second `msg_id` would raise
`TypeError` and kill the node. Also, the client's id belongs to the
client→n1 exchange; n1→n0 needs a fresh one.

**C6. Why does `relay` remove `msg_id` and `in_reply_to`?**
Same reason: `reply` adds its own `in_reply_to` and `_send` its own
`msg_id`. Duplicates would cause a `TypeError`. What's left is n0's actual
answer.

**C7. Why `getattr(body, 'from')`?**
`from` is a Python keyword, so `body.from` is a syntax error.

**C8. Why `global node_id, node_ids` in `handle` but not in `forward` or
`propagate`?**
Assigning to a module variable inside a function needs `global`; only
reading it doesn't.

**C9. What does `propagate` do, and why `send` and not `rpc`?**
It sends `update{key, value}` to every other node. `send` is fire and
forget: n0 doesn't wait for acknowledgements, which is why a crashed backup
blocks nothing.

**C10. Why is `propagate` before `reply` in `execute`? Would swapping them
change anything?**
No. Propagation is not awaited and backups are never read, so the order
doesn't affect correctness or the client's latency in any meaningful way.

**C11. How does the same program know whether it's the primary?**
`node_id` comes from the `init` message; line 40 compares it with
`PRIMARY = 'n0'`.

**C12. What does `MS_CRASH="n0@5"` do, exactly?**
`ms.py` on n0 reads the variable at init. From 5 s on it drops every
received message, sends nothing and runs no timers, but the process stays
alive, so Maelstrom doesn't notice. To everyone else, n0 just goes silent.
→ `03-ms-py.md` §6

**C13. Why do `trace` and `logging` write to stderr?**
stdout *is* the network (Maelstrom reads messages from it). stderr goes to
the node log.

---

## D. The runs

**D1. Single server crash: valid? available?**
Valid (no wrong answers), unavailable after 5 s (0 ok; 15 info, timed-out
reads as fail). → `07-results-explained.md`

**D2. Explain the anomaly with three independent `kv.py`s.**
p3 wrote 2 at n0 (acknowledged), p0 read 2 at n0, then p2 read 0 at n2,
which never heard of the write. No single order explains both reads: "can't
read 0 from register 2". → `../02-single-server.md` §4

**D3. Results of D under each scenario?**
Valid in all 19 runs. Available: everything (no faults, latency), nobody
(n0 crash), all but n1's clients (n1 crash), only clients whose server can
reach n0 (partition). → `07-results-explained.md`

**D4. Which prediction was wrong and why?**
Latency: we predicted about 200 ms for forwarded requests (4 delayed
messages). We observed about 108 ms: `--latency` delays only
server↔server messages, so it's 2 delayed hops. → `../04-build-and-test.md`

**D5. All your runs were valid. Why is that not a coincidence?**
The argument of B3 is independent of timing: one executor, one copy, the
only one read. Faults can only remove answers. We repeated each scenario 3×
and with higher latency and rate to try to break it.

**D6. Describe an `info` write that actually happened.**
`runs/p4-partition-2`: an asymmetric partition let n1's forward reach n0
(executed at 3.212 s) but dropped n0's reply. p0 then read the value
(3.293 s), but p16 recorded `info` (4.210 s). The checker linearized the
write before p0's read, so the run was valid. → `../05-explain-execution.md` §2

**D7. Your revised claim?**
Under crash-stop, delays, reordering and partitions (no duplication or
amnesia), D is linearizable for any number of failures, including n0's.
Clients of n0, and of servers connected to n0, get answers. If n0 is down,
nobody does. Evidence: 19 valid runs. Not covered: failover, n0 restarting
without memory, duplicated messages. → `../05-explain-execution.md` §6

---

## E. Extend / compare (Part 6)

**E1. Is any strategy correct in every scenario? Available in every
scenario? Both?**
Correct: D. Most available: A. Both: none, and none can be (CAP).

**E2. What does B buy and what does it cost?**
Buys: an acknowledged write is on every copy. Costs: the slowest server sets
the latency, and one crashed server blocks all writes everywhere.

**E3. n0 crashes. How could another server take over safely?**
(1) The new primary must have every acknowledged write, so n0 must wait for
backups' acks before replying, and updates need sequence numbers. (2) Never
two primaries: agree on the new primary by majority vote, number the
primaries (epochs/terms), reject messages from old ones, and have a primary
that can't reach a majority stop answering. → `01-theory.md` §11

**E4. Middle ground between waiting for one and waiting for all?**
A majority quorum. With 3 nodes, wait for 2: any two majorities intersect,
and it tolerates 1 crash. In general R + W > N. → `01-theory.md` §11

**E5. What would break D's correctness?**
Adding failover without the mechanisms of E3 (a backup with a stale or
reordered copy answers, or split brain). n0 restarting without memory.
Duplicated messages re-executing an old write.

**E6. If you could add one mechanism to D, which, and what would it cost?**
For example: n0 waits for one backup's ack before replying, plus sequence
numbers. Then that backup has every acknowledged write. Cost: latency, plus
blocking if that backup is down, unless n0 waits for "any 1 of 2", which is
a majority with n0. Still needs agreement on who takes over.

**E7. What happens to D with 5 nodes?**
The same properties. More updates per write (4), still correct, still as
available as n0.

---

## F. About the AI usage (deliverable item 5)

**F1. What did the AI do, and what did you check?**
Be honest and specific: see `../ai-log.md`. The examiner can ask you to
explain any line, so "the AI wrote it" isn't an answer. You must be able to
explain it yourself.

**F2. What did you have to correct or reject?**
Fill in `../ai-log.md` with your own decisions. One concrete design point to
discuss: the "no timeout" choice, and why error 11 would have been wrong
while error 13 would have been acceptable.
