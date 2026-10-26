# 7 · The results, explained number by number

`../04-build-and-test.md` lists what we observed. This file explains **why**
each number is what it is, connecting it to the code (`05-d-py.md`) and the
theory (`01-theory.md`). If you can reproduce these explanations on your
own, you understand the lab.

All numbers come from `results/results.tsv` and the copies in `runs/`.

---

## How to read a line of `results.tsv`

```
d.py	crash-n0	valid	32	61	45	store/lin-kv/20261016T180005.296+0100
│       │          │      │   │   │   └ where the evidence is
│       │          │      │   │   └ info: write/cas with unknown outcome
│       │          │      │   └ fail: definite "no" (error 20/22) or a timed-out read
│       │          │      └ ok: completed successfully
│       │          └ checker verdict (linearizable?)
│       └ scenario (scenarios.sh name)
└ program
```

Rule of thumb: **valid/INVALID = correctness. ok vs info+fail =
availability.**

---

## Part 2: `kv.py`

### `single`: valid, 152 / 60 / 0

- **valid**: one dict, one thread, so each handler call is a linearization
  point (`04-kv-py.md`).
- **60 fail, 0 info**: all fails are correct answers. Most are cas with the
  wrong `from` (error 22, since values are random 0–4, a cas usually
  mismatches) plus a few reads/cas before the key was first written (error
  20). Nothing timed out, so there are no `info`.

### `single-crash`: valid, 33 / 25 / 15

- Before 5 s: normal operation, which accounts for all **33 ok**.
- At 4.957 s n0 "crashes" (`ms.py` drops everything).
- After that, every request waits for the **1 s client timeout**:
  - timed-out **write/cas** → **info**: 15 of them, about one per second
    for the 15 remaining seconds. Each info retires the process, so the
    numbers climb p1 → p3 → … → p29;
  - timed-out **read** → **fail**: part of the 25.
- **valid** because an unanswered request can't be wrong.
- `:ok-fraction` 0.45: fewer than half the operations completed.

### `independent`: INVALID, 152 / 58 / 0

- Same program, 3 nodes. Every node answers instantly from its own dict, so
  **availability is perfect** (0 info).
- **INVALID**: client p2 read 0 at n2 after p3's `write(0,2)` at n0 was
  acknowledged (and after p0 had already read 2). It's a stale read.
  `linear.svg`: "can't read 0 from register 2".
- This is the **available but incorrect** corner. D will be the
  **correct but not always available** corner.

---

## Part 4: `d.py`, 19 runs, all valid

### Why **every** verdict is `valid`

One structural reason (`01-theory.md` §9): every answer comes from
`execute()` on n0 (`d.py` lines 68–102), one at a time, on one dict. No
code path reads a backup. Faults only **remove** or **delay** messages, so
they turn answers into "no answer" (`info`/`fail`) and never into a wrong
answer. That's why we ran 19 times and expected 19 valid, rather than
hoping for it.

### `nofaults`: 150/59/0 · 160/50/0 · 125/74/0

- 0 info: every request answered well within 1 s.
- Latency: **2 ms** median for n0's clients (2 messages), **4 ms** for the
  backups' clients (4 messages: client→backup→n0→backup→client).
- The ok/fail split varies between runs only because the random workload
  differs (how many cas, which values).

### `latency` (`--latency 50 --rate 50`): 744/270/0 · 698/270/0 · 711/295/0

- 5× the rate means about 5× the operations (~1000 per run).
- Still **0 info**: the slowest operation took 165 ms, far below 1 s.
- Median latency: **8 ms** for n0's clients, **108 ms** for the backups'
  clients. The difference, about 100 ms, is two delayed hops of about 50 ms
  each (backup→n0 and n0→backup).
- **Our wrong prediction:** we expected about 200 ms (four delayed
  messages). The data shows client↔server messages are not delayed by
  `--latency`, only server↔server ones. The verdict and availability
  predictions were right.
- More load doesn't matter to correctness: n0 still executes everything one
  at a time, just more of them.

### `latency-high` (`--latency 100 --rate 100`): ~1030/~365/0, ×3

The same story, twice as slow: backups' clients ~221 ms median, max
301 ms. Still below the 1 s timeout, so 0 info. We tried harder to break D
(guide Part 4.3) and could not, as the structural argument predicts.

### `crash-n0` (`MS_CRASH="n0@5"`): 32/61/45 · 47/55/45 · 28/71/44

- Before 5 s: normal (all the ok's).
- After 5 s: **0 ok anywhere**. Clients of n0 get nothing (n0 drops
  everything). Clients of n1/n2: the backups still `forward` (we see the
  traces after 5 s), but n0 never answers, so `relay` never runs.
- The ~45 info: there are **3 nodes × 2 processes**, each timing out once
  per second for ~15 s, giving about 90 timed-out operations. About half
  were writes/cas (**info**, ~45) and half reads (**fail**, inside the
  ~60 fail). From `runs/p4-crash-n0`: after the crash, **15 fail + 15 info
  for each of n0, n1, n2**, perfectly symmetric, because every server is
  equally dead to its clients.
- **valid ×3.** The surviving copies on n1/n2 are useless: under D they
  may not answer from them.
- Code responsible: `PRIMARY = 'n0'` is fixed (line 26); `rpc` has no
  timeout (line 66); there is no failover.

### `crash-n1` (`MS_CRASH="n1@5"`): 137/61/9 · 129/58/6 · 120/69/8

- Clients of n0 and n2: unaffected (in `runs/p4-crash-n1` after the crash:
  n0's 79 ok, n2's 25 ok, **0 info**).
- Clients of n1: **0 ok, 9 fail, 9 info** after 5 s. n1 drops their
  requests.
- Only ~⅓ of the clients lose service, so info is ~6–9 instead of ~45.
- Why n0 doesn't notice: `propagate` uses **`send`** (fire and forget,
  line 107). n0 never waits for n1, so a dead backup can't block anything.
  (Compare strategy B, where it would block every write.)
- n1's copy misses every update after 5 s, which doesn't matter because
  nobody reads it.

### `partition` (`--nemesis partition`): 124/55/8 · 117/72/10 · 143/53/4

The nemesis picks a different pattern each run, so the numbers differ more:

| run | what was cut | effect |
|---|---|---|
| `p4-partition` | 11.1 s → end: **n0 \| n1 n2** | n0's clients 49 ok; n1's and n2's 0 ok, 8 info. Forwards were dropped, so writes were never executed |
| `p4-partition-2` | 0–7.4 s: **asymmetric ring** (n1 can't hear n0, n0 can't hear n2, n2 can't hear n1) | n1's forwards *reach* n0 and **are executed**, but the replies are dropped. Some info writes **took effect** (one was read by another client) |
| 3rd run | late asymmetric ring | 4 info |

- **valid ×3**: dropped forward → not executed → info; dropped reply →
  executed → info. Both are allowed outcomes of an info.
- Clients are never cut off from **their own** server. Maelstrom's
  partitions are only between servers. So the backups keep logging
  `forward`.
- This is **CAP** in action: on the side without n0, D chooses consistency
  (no answer) over availability (`01-theory.md` §10).
- Hidden effect: at the end of `p4-partition`, n2's copy holds 4 while n0's
  holds 3, so the copies diverged. That's invisible under D.

### `pause-n0` (`MS_CRASH="n0@5-12"`): 95/55/21

| window | ok | fail | info | why |
|---|---|---|---|---|
| 0–5 s | 47 | 7 | 0 | normal |
| 5–13 s | 5 | 28 | 21 | n0 drops everything from 4.967 s to 11.967 s: **not one ok** in that interval; the few ok of this window all come after the recovery (first at 12.688 s) |
| after 13 s | 43 | 20 | 0 | normal again |

- n0 keeps its memory (`ms.py` only stops I/O), so after 12 s its `store`
  is intact and answers are correct. First ok after recovery: 12.688 s.
- Requests sent during the pause are **lost, not delayed**: `ms.py` reads
  them and throws them away (`receiveAll`, lines 60–62). They don't
  "come back" after 12 s.
- **valid**: the pause looks like a crash followed by a recovery with all
  state intact. If n0 recovered **without** its memory, this run would be
  invalid, but we can't inject that.

---

## The pattern across all runs

| | correctness | availability |
|---|---|---|
| `kv.py`, 1 node | ✔ | ✔ until it crashes, then ✘ |
| `kv.py`, 3 nodes | **✘** | ✔ always |
| `d.py`, 3 nodes | **✔ always** | ✔ only for clients whose server can reach n0 |

**D = a single server with extra hops.** It traded the "copies disagree"
problem of independent servers for the single point of failure of one
server. It added *latency* (two hops) and *messages* (updates), and **no
fault tolerance at all**. That is the lesson of the lab for strategy D, and
the motivation for quorums, failover and consensus in the next labs.
