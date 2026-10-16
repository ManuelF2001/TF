# Fault-Tolerant Distributed Systems — practical work

```
TF/
├── README.md        this file
├── env.sh           puts Java 17 + gnuplot on the PATH (user-space install)
├── archives/        original downloads (kit.tar.bz2, maelstrom.tar.bz2)
├── kit/             course kit, unmodified (ms.py, run.sh, timeline.py, record.tex, ...)
├── maelstrom/       Maelstrom 0.2.4, unmodified
└── lab1/            Lab 1 — From one server to naive replication (group strategy D)
```

`kit/` and `maelstrom/` are kept exactly as distributed so that they can be
re-extracted at any time; all our work is in `lab1/` (and later `lab2/`, …).

## Setup on this machine

Java and gnuplot were installed without sudo into `~/.local/opt`
(`~/.local/bin/gnuplot` is a small wrapper). Before running anything:

```bash
source ~/TF/env.sh
```

(The lab scripts do this automatically.) With sudo, the standard install
`sudo apt install openjdk-17-jre-headless gnuplot-nox graphviz` makes
`env.sh` unnecessary.

Installation check (from the guide), inside `kit/`:

```bash
./run.sh echo echo.py      # ends with "Everything looks good!"
```

## Lab 1

Start at [`lab1/README.md`](lab1/README.md).
