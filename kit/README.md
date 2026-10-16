# Fault Tolerance lab kit

Requirements: Python 3.8 or later and Maelstrom 0.2.4
(https://github.com/jepsen-io/maelstrom/releases/tag/v0.2.4), installed as
described in https://github.com/jepsen-io/maelstrom/blob/main/doc/01-getting-ready/index.md
(Java 17 or later, `gnuplot`, `graphviz` and a working `git`, which Maelstrom
calls). Place this `kit` directory next to the `maelstrom` directory, or set
`MAELSTROM` to the `maelstrom` script.

| file | purpose |
|---|---|
| `ms.py` | helpers for node programs (messages, rpc, timers, trace, crash injection) |
| `echo.py` | smallest possible node |
| `echoplus.py` | example of rpc, timers and trace events |
| `run.sh` | runs a Maelstrom test with the course defaults |
| `timeline.py` | merges the trace events of a run; `--history` adds client operations and partitions |
| `record.tex` | template for the lab record (deliverable) |
| `AGENTS.md` | context for AI assistants (`CLAUDE.md` points to it) |

Quick check:

```
./run.sh echo echo.py
MS_CRASH="n1@2-4" ./run.sh echo echoplus.py --time-limit 6
./timeline.py --history
```

If you use an AI assistant, give it `AGENTS.md` as context (tools such as
Codex, Copilot and Cursor read it automatically; Claude Code reads `CLAUDE.md`).
