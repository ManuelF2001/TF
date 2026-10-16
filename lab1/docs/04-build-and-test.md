# Part 4 – Build and test

Code: `code/d.py` (design in `03-design-strategy-D.md`, line-by-line
explanation in `code.md` §3). Every run below is a line of
`results/results.tsv`; one run per scenario is copied to `runs/`.

Commands (from `lab1/`; `scenarios.sh` does exactly this and records the
result):

```bash
../kit/run.sh lin-kv code/d.py                              # no faults
../kit/run.sh lin-kv code/d.py --latency 50 --rate 50       # latency, more load
MS_CRASH="n0@5" ../kit/run.sh lin-kv code/d.py              # primary crashes
MS_CRASH="n1@5" ../kit/run.sh lin-kv code/d.py              # another server crashes
../kit/run.sh lin-kv code/d.py --nemesis partition          # network partitions
```

## 1. Results: prediction vs. observation

Each scenario was run **3 times** (guide, Part 4.3). Counts are
ok / fail / info per run.

| scenario | predicted | observed verdicts | ok / fail / info | clients completing operations | prediction right? |
|---|---|---|---|---|---|
| No faults | valid; all complete | **valid ×3** | 150/59/0 · 160/50/0 · 125/74/0 | all; 0 info | yes |
| `--latency 50 --rate 50` | valid; slower | **valid ×3** | 744/270/0 · 698/270/0 · 711/295/0 | all; 0 info | yes (detail wrong, see §2) |
| `MS_CRASH="n0@5"` | valid; nobody after 5 s | **valid ×3** | 32/61/45 · 47/55/45 · 28/71/44 | **0 ok after the crash**, at any server | yes |
| `MS_CRASH="n1@5"` | valid; only n1's clients stop | **valid ×3** | 137/61/9 · 129/58/6 · 120/69/8 | n0's and n2's clients: all; n1's: **0 ok** after 5 s | yes |
| `--nemesis partition` | valid; clients cut off from n0 stop | **valid ×3** | 124/55/8 · 117/72/10 · 143/53/4 | n0's: all; others: only while connected to n0 | yes |

**Trying harder to break it** (guide: "if all runs are valid, try increasing
`--rate` and `--latency`"):

| scenario | verdicts | ok / fail / info |
|---|---|---|
| `--latency 100 --rate 100` | **valid ×3** | 1039/361/0 · 1017/378/0 · 1026/356/0 |
| `MS_CRASH="n0@5-12"` (n0 paused, memory kept) | **valid ×1** | 95/55/21 |

Reading the counts:

- `fail` is not an error of our store: it contains `cas` mismatches (22),
  operations on a key not yet written (20), and **reads that timed out** —
  Maelstrom records a timed-out read as `fail` (a read has no effect, so
  "did not happen" is safe), and only timed-out `write`/`cas` as `info`.
- `info` = a `write`/`cas` whose client got no answer within Maelstrom's
  1 s client timeout.

## 2. Details per scenario

### No faults

Every request is executed once at n0 (`execute` trace), and backups relay
the answer (`forward` → `execute src="n1"` → `relay`). From
`runs/p4-nofaults`:

```
0.625  p1  invoke   read [0 nil] -> n1
0.627  n1  forward  key=0 op="read" client="c7"
0.628  n0  execute  key=0 op="read" value=0 src="n1"
0.630  n1  relay    key=0 op="read" client="c7" result="read_ok"
0.630  p1  ok       read [0 0]
```

Latency: median 2 ms for n0's clients, 4 ms for the backups' clients.

### Latency 50 ms, rate 50

| clients of | median | p95 | max |
|---|---|---|---|
| n0 | 8 ms | 46 ms | 61 ms |
| n1, n2 | 108 ms | 146 ms | 165 ms |

(`latency 100, rate 100`: n0 2 ms / backups 221 ms median, max 301 ms.)

**Where the prediction was wrong (detail).** We predicted ≈ 200 ms for
forwarded requests (4 delayed messages: client→n1→n0→n1→client). The
observed ≈ 100 ms shows that **`--latency` only delays messages between
servers**, not client↔server messages: a forwarded request pays 2 delayed
hops, a request to n0 none. The verdict and availability predictions were
right — all well below the 1 s client timeout, 0 `info`.

The higher rate gives many more concurrent operations (~1000 ok), but they
are still executed one at a time by n0's single handler thread, so the
verdict cannot change.

### Primary crashes (`MS_CRASH="n0@5"`)

`runs/p4-crash-n0`: n0 stops at 4.957 s. Outcomes per server's clients
after the crash:

| clients of | ok | fail | info |
|---|---|---|---|
| n0 | 0 | 15 | 15 |
| n1 | 0 | 15 | 15 |
| n2 | 0 | 15 | 15 |

The backups keep forwarding (`forward` events after 5 s) but never get an
answer to `relay`. **Total unavailability; still valid.** The 3 surviving
copies are useless: n1 and n2 hold a copy of the data but, under D, may not
answer from it.

### Another server crashes (`MS_CRASH="n1@5"`)

`runs/p4-crash-n1`, after n1 stops at 4.970 s:

| clients of | ok | fail | info |
|---|---|---|---|
| n0 | 79 | 31 | 0 |
| n1 | **0** | 9 | 9 |
| n2 | 25 | 7 | 0 |

n0 does not wait for n1 (fire-and-forget updates), so only n1's own
clients lose service.

### Network partitions (`--nemesis partition`)

Maelstrom's partition nemesis chooses a different pattern each time:

| run | partitions (time: who drops messages from whom) | info |
|---|---|---|
| `p4-partition` | 0.0–4.8 s: none isolated (empty); **11.1 s – end: n0 \| n1 n2** | 8 |
| `p4-partition-2` | 0.0–7.4 s: **asymmetric ring** n1←n0, n0←n2, n2←n1; 8.9–9.1 s: n0 \| n1 n2 | 10 |
| 3rd run | 0.0–13.1 s: none isolated; 16.4 s – end: asymmetric ring | 4 |

Observed in `p4-partition`, from 11.144 s to the end: n0's clients 49 ok,
n1's and n2's **0 ok**; no forwarded request reached n0; no update reached
a backup. Clients themselves are never cut off from their own server: the
partitions are only between servers. The detailed explanation of this run
is Part 5 (`05-explain-execution.md`).

With the asymmetric ring, n1's forwards *do* reach n0 and are executed,
but the replies are dropped: those `info` operations **took effect**
(one was even read by another client, see Part 5).

### Pause (`MS_CRASH="n0@5-12"`)

`runs/p4-pause-n0`: n0 down from 4.967 s to 11.967 s, memory kept.

| window | ok | fail | info |
|---|---|---|---|
| 0 – 5 s | 47 | 7 | 0 |
| 5 – 13 s | 5 | 28 | 21 |
| after 13 s | 43 | 20 | 0 |

Service resumes as soon as n0 is back (first `ok` after recovery at
12.688 s); requests sent during the pause are lost, not delayed.

## 3. Trace events

`d.py` traces `forward`, `execute`, `propagate`, `apply` and `relay`
(`code.md` §3). Useful commands:

```bash
../kit/timeline.py --history                     # last run, everything
../kit/timeline.py runs/p4-partition --history --key 0
../kit/timeline.py runs/p4-crash-n0 --event crash --event forward --event relay
../kit/timeline.py runs/p4-partition --history --process 5
```

## 4. Summary

- **Correctness:** valid in all 19 runs of strategy D, under every
  scenario, including the heavier load. This is expected from the design:
  one copy, one executor, the only one read (`theory.md` §6).
- **Availability:** exactly as good as n0. With n0 down: nothing. With a
  backup down or cut off from n0: that backup's clients get nothing; all
  others are unaffected.
- **Wrong prediction:** only the latency estimate (2 delayed hops, not 4).
