# Lab 1 explained: from theory to every line of code

A complete, slow-paced explanation of Lab 1 (group strategy **D**, "primary
for everything"). It goes from the theory, through the test machine
(Maelstrom) and every line of the code, to why each result came out the way
it did.

The other files in `docs/` are the **answers** to the guide (Parts 0–6, the
exit record, the AI log). This folder is the **explanation** behind them:
read it to be able to defend the work in the individual discussion.

## Reading order

| # | file | what you learn | time |
|---|---|---|---|
| 1 | [`01-theory.md`](01-theory.md) | distributed systems basics, linearizability (with examples), ok/fail/info, safety vs liveness, failure and timing models, replication strategies A–D, why D is correct, CAP, quorums, consensus, glossary | 40 min |
| 2 | [`02-maelstrom.md`](02-maelstrom.md) | what happens when you run a test: processes, stdin/stdout, message format, `msg_id`/`in_reply_to`, nodes vs processes vs client ids, the output files, `results.edn` annotated | 20 min |
| 3 | [`03-ms-py.md`](03-ms-py.md) | every line of the helper library: the single worker thread, `send`/`reply`/`rpc`, how replies find their callback, how a crash is simulated | 30 min |
| 4 | [`04-kv-py.md`](04-kv-py.md) | every line of the single-server store (Part 2) and why it is correct with 1 node and wrong with 3 | 15 min |
| 5 | [`05-d-py.md`](05-d-py.md) | **every line of strategy D**, real messages from our runs traced through the code, which line causes which result, and "what if" questions | 40 min |
| 6 | [`06-scripts.md`](06-scripts.md) | every line of `env.sh`, `run.sh`, `scenarios.sh`, `run_all.sh`, and how `timeline.py` works | 20 min |
| 7 | [`07-results-explained.md`](07-results-explained.md) | every number in `results.tsv` explained | 20 min |
| 8 | [`08-exam-prep.md`](08-exam-prep.md) | ~45 likely questions for the individual discussion, with short answers | self-test |

If you're short on time, read `01` §4, §5 and §9, then `05` and `08`.

## The whole lab in ten lines

1. **Service:** a key-value store with read, write and cas. "Correct" means
   **linearizable**: it behaves like one copy where each operation happens
   instantly while the client waits.
2. **One server** (`kv.py`) is correct but dies with its server: valid,
   0 ok after the crash.
3. **Three independent servers** are available but wrong: a stale read,
   INVALID.
4. **Strategy D:** every request goes to n0; n0 executes it, sends the new
   value to the backups without waiting, and replies; backups relay.
5. **Always correct:** only n0 answers, one request at a time, from one
   copy. Faults can only remove answers. 19/19 runs valid.
6. **Only as available as n0:** n0 down means nobody is served; a backup
   down or cut off means its own clients aren't served.
7. A client that gets no answer can't know whether its write happened
   (`info`). We saw both kinds: forwards lost (not executed) and replies
   lost (executed and even read by others).
8. The backups' copies silently diverge (no acks, no ordering), which is
   invisible because nobody reads them.
9. **D = a single server with extra hops.** It removed the inconsistency of
   independent copies and kept the single point of failure.
10. **Next:** safe failover needs acknowledged updates, ordering, and
    majority agreement on the primary, which is the road to quorums and
    Raft.

## Files this folder explains

```
lab1/code/kv.py      → 04-kv-py.md
lab1/code/d.py       → 05-d-py.md
lab1/code/ms.py      → 03-ms-py.md   (course kit, unmodified copy)
lab1/scenarios.sh    → 06-scripts.md
lab1/run_all.sh      → 06-scripts.md
kit/run.sh           → 06-scripts.md
kit/timeline.py      → 06-scripts.md
env.sh               → 06-scripts.md
lab1/runs/, results/ → 07-results-explained.md
```
