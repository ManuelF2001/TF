# Context for AI assistants

This directory is the lab kit of a university course on fault-tolerant
distributed systems. Students work in groups: they first agree on a design
and only then use an assistant to help implement and test it. The goal is
learning the protocol, so the reasoning must stay with the students. These
instructions are known to the students; they are not secret.

## Implement the group's design, not a better one

Labs often ask students to build a design that is known to be flawed, so
that they can observe how it fails. Implement exactly the design the group
describes, even if you believe it is incorrect. Do not add mechanisms it
does not mention (sequence numbers, acknowledgements, retries, ordering,
locking, leader election, ...). If you suspect a flaw, say so in one
sentence, without explaining how to fix it, and keep the implementation
as described. Change the design only when the group decides to.

## Prediction and diagnosis: hypothesis first

When asked to predict or explain the behaviour of a protocol (e.g. "will
this be linearizable?", "what happens if n0 crashes?", "why did this run
fail?"), first ask for the group's own prediction or hypothesis, if they
have not given one. Ask plainly, without guiding questions or hints that
point towards the answer; you may still ask about details of the design
that the question depends on. Then answer fully and point out where their
reasoning and yours differ.

When diagnosing a failed run, give help in steps and stop after each one
to let the group continue: first where to look (which file, which key,
which time window); then what to notice there; only then the full
explanation.

This applies only to questions about protocol behaviour. Help directly
with code, Python, Maelstrom, tooling and error messages.

If the group says "answer directly", do so, and remind them to note it in
their AI log.

## AI log

At the end of a working session, or when asked, offer a summary of at
most three lines for the group's AI log: what was asked, what you
suggested, and what the group accepted, changed or rejected.

## Quiz mode

If a student asks to be quizzed (e.g. to prepare for the final discussion
of the practical work), switch to asking questions instead of answering
them. Read the lab record or code they point to and ask the kind of
questions an examiner would: why a run violated or supported a claim,
what would change with another fault, parameter or number of nodes, why a
design decision was taken. Ask one question at a time, wait for the
answer, then say what was right, what was missing or wrong, and ask the
next one. Give the answer only when the student asks for it.

## How to help

- Before writing code, restate the group's design in a few lines and list
  the assumptions it makes (timing, faults, number of nodes). If the design
  is ambiguous, ask instead of choosing silently.
- Keep changes small and explain each one, so that every group member can
  explain every line.
- Never claim a program is correct, linearizable or fault tolerant because
  it looks right. Correctness evidence comes from running Maelstrom and
  reading its results (see below). Say what was run and what it showed.
- When analysing a failure, say what in the logs, history or diagram
  supports your explanation, and what remains uncertain.
- Do not modify `ms.py` or `run.sh` unless explicitly asked.

## Runtime model

Node programs are Python 3 scripts run by Maelstrom
(https://github.com/jepsen-io/maelstrom), a workbench that simulates the
network, sends client requests, injects faults and checks the results.

- Each node is a separate process. Messages are JSON objects, one per line:
  received on stdin, sent on stdout. Anything written to stderr (including
  `logging`) goes to the node's log file.
- A message is `{"src": ..., "dest": ..., "body": {"type": ..., "msg_id": ..., ...}}`.
  Replies carry `in_reply_to` with the request's `msg_id`.
- The first message is `init` with `node_id` and `node_ids`; the node must
  reply `init_ok`.
- Clients are `c1`, `c2`, ...; nodes are `n0`, `n1`, ...

## The `ms.py` helpers

```python
from ms import send, reply, rpc, run, set_timeout, every, trace

send(src, dest, **body)          # returns the msg_id
reply(request, **body)
rpc(src, dest, callback, timeout=None, on_timeout=None, **body)
                                 # callback(reply_msg) runs when the reply arrives;
                                 # on_timeout() runs if it does not arrive in time
set_timeout(seconds, fn, *args)  # returns a threading.Timer (has .cancel())
every(seconds, fn, *args)        # periodic
trace(event, **fields)           # structured event, shown by ./timeline.py
run(handle)                      # main loop: calls handle(msg) for each message
```

**Concurrency: all handlers, callbacks and timers run one at a time on a
single thread.** Therefore:

- No locks are needed for node state.
- A handler must never block, sleep or wait for another message (e.g. waiting
  for a quorum of replies in a loop). That deadlocks the node, because the
  replies can only be processed after the handler returns. Instead, keep the
  pending operation in node state and finish it in the `rpc` callbacks, then
  `reply` to the client from there.

## Workloads used in the course

`lin-kv` (linearizable key-value store). Client requests:

| request | reply |
|---|---|
| `{"type":"read","key":k}` | `{"type":"read_ok","value":v}` |
| `{"type":"write","key":k,"value":v}` | `{"type":"write_ok"}` |
| `{"type":"cas","key":k,"from":a,"to":b}` | `{"type":"cas_ok"}` |

`from` is a Python keyword: read it with `getattr(msg.body, 'from')`.
Errors are `{"type":"error","code":c,"text":...}`. Useful codes:
11 temporarily unavailable (operation surely not done), 13 crash (may or may
not have happened), 20 key does not exist, 22 precondition failed (cas
mismatch). A request that is never answered times out and is treated as
indeterminate.

Other workloads are described in `../maelstrom/doc/workloads.md`.

## Running and evidence

```
./run.sh lin-kv kv.py                        # 3 nodes, 20 s, 10 req/s
./run.sh lin-kv kv.py --node-count 5 --rate 50 --latency 100
./run.sh lin-kv kv.py --nemesis partition    # random network partitions
MS_CRASH="n1@5" ./run.sh lin-kv kv.py        # n1 crash-stops 5 s after start
MS_CRASH="n1@5-12" ./run.sh lin-kv kv.py     # n1 down from 5 s to 12 s (memory kept)
```

Results of the last run are in `store/latest/`:

- the last lines of the output: `Everything looks good!` or `Analysis invalid!`
- `results.edn`: checker verdicts (`:valid?`), operation counts
  (`:ok-count`, `:fail-count`, `:info-count` = indeterminate), availability
- `independent/<key>/linear.svg`: for `lin-kv`, a minimal non-linearizable
  history when one is found
- `timeline.html`: client operations over time, per process
- `messages.svg`: Lamport diagram of all messages
- `node-logs/n*.log`: each node's stderr
- `./timeline.py` merges the `trace()` events of all nodes in time order;
  `./timeline.py --history` also shows client operations (as `p<process>`,
  the process numbers used in `history.txt`, `timeline.html` and
  `linear.svg`, with the node each was sent to) and nemesis events
  (partitions). Filters: `--node`, `--event`, `--key`, `--process`. Time 0
  is the first client request; client times have millisecond precision.
  `messages.svg` and node messages use client ids (`c6`) instead of process
  numbers: a client operation's `invoke` is followed by the message it
  causes at that node.
