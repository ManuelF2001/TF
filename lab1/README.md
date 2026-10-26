# Lab 1 – From one server to naive replication (group strategy **D**)

Guide: [`lab1.pdf`](lab1.pdf). Deliverable due **Friday, 30 October**:
lab record (≤ 2 pages, `record/record.tex`) + code + the `store/` runs it
cites.

**Strategy D — primary for everything:** every request is forwarded to n0,
which executes it and sends the update to the others.

## Results at a glance

| scenario | runs | verdict | availability |
|---|---|---|---|
| single server (`kv.py`, 1 node) | 1 | valid | all |
| single server, crash at 5 s | 1 | valid | **none** after the crash |
| 3 independent servers (`kv.py`) | 1 | **INVALID** (stale read) | all |
| D, no faults | 3 | valid ×3 | all |
| D, `--latency 50 --rate 50` | 3 | valid ×3 | all (backups ~108 ms) |
| D, n0 crashes | 3 | valid ×3 | **none** after the crash |
| D, n1 crashes | 3 | valid ×3 | all but n1's clients |
| D, partitions | 3 | valid ×3 | only clients of servers that can reach n0 |
| D, `--latency 100 --rate 100` (extra) | 3 | valid ×3 | all |
| D, n0 paused 5–12 s (extra) | 1 | valid | none during the pause, then all |

D is **always correct and as available as n0**: it is a single server with
extra hops. Full table with counts: `docs/04-build-and-test.md`; raw
lines: `results/results.tsv`.

## Layout

```
lab1/
├── README.md                this file
├── lab1.pdf                 the lab guide
├── code/
│   ├── kv.py                Part 2: single-server lin-kv node
│   ├── d.py                 Parts 3-4: strategy D
│   └── ms.py                unmodified copy of kit/ms.py (must sit next to the programs)
├── docs/                    answers to every part of the guide
│   ├── theory.md            linearizability, ok/fail/info, fault models, CAP, quorums
│   ├── code.md              line-by-line explanation of kv.py, d.py and the scripts
│   ├── 00-predict.md        Part 0 – predictions
│   ├── 01-specification.md  Part 1 – specification, assumptions, first claim
│   ├── 02-single-server.md  Part 2 – one server, crash, three independent servers
│   ├── 03-design-strategy-D.md  Part 3 – space-time diagram, open details, predictions
│   ├── 04-build-and-test.md Part 4 – results of every scenario vs. predictions
│   ├── 05-explain-execution.md  Part 5 – one execution explained, revised claim
│   ├── 06-compare.md        Part 6 – class table and discussion questions
│   ├── 07-exit-record.md    Exit record (four lines)
│   ├── ai-log.md            AI log (deliverable item 5)
│   └── explained/           in-depth explanation: theory, Maelstrom, every line
│                            of ms.py / kv.py / d.py / scripts, results, exam prep
├── record/
│   ├── record.tex           the filled-in lab record (2 pages)
│   └── record.pdf           compiled
├── runs/                    copies of the runs cited (one per scenario)
├── results/results.tsv      one line per run: program, scenario, verdict, ok, fail, info, store dir
├── scenarios.sh             run one scenario N times and record it
├── run_all.sh               rerun everything (~15 min)
└── store/                   all raw Maelstrom runs (not submitted)
```

Suggested reading order: `theory.md` → `00` … `07` → `code.md`.
For the full, slow explanation (theory to every line of code), start at
`docs/explained/README.md`.

## Running

From `lab1/` (in WSL):

```bash
source ../env.sh                               # Java + gnuplot (see ../README.md)
../kit/run.sh lin-kv code/d.py                 # one run; results in store/latest
MS_CRASH="n0@5" ../kit/run.sh lin-kv code/d.py
../kit/timeline.py --history                   # trace of the last run
../kit/timeline.py runs/p4-partition --history --key 0

bash scenarios.sh code/d.py partition 3        # run a scenario 3x, append to results.tsv
bash run_all.sh                                # everything in the documents
```

Scenario names: `single`, `single-crash`, `independent`, `nofaults`,
`latency`, `latency-high`, `crash-n0`, `crash-n1`, `partition`, `pause-n0`.

Compile the record: `cd record && tectonic record.tex` (Tectonic is in
`~/.local/bin`), or upload `record.tex` to Overleaf.

## Before submitting — what the group still has to do

- [ ] Fill in the group number, member names and **Contributions** in
      `record/record.tex`.
- [ ] Each member: compare your own Part 0 answers with `docs/00-predict.md`.
- [ ] Check that the design decisions in `docs/03-design-strategy-D.md` §2
      are what the group wants; if not, change them in `code/d.py` and rerun.
- [ ] Complete `docs/ai-log.md` and §5 of the record with what *you*
      accepted, changed or rejected (and the optional partition question,
      asked in a fresh AI session).
- [ ] Every member can explain every line of `code/d.py` (`docs/code.md`):
      the final discussion is individual.
- [ ] Replace the A/B/C rows of `docs/06-compare.md` with the class results.
- [ ] Submit: `record/record.pdf` (and `.tex`), `code/`, and the cited runs
      (`runs/p4-partition`, `runs/p4-partition-2`, and the other `runs/`
      folders behind the table).
