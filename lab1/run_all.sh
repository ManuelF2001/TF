#!/usr/bin/env bash

# Reproduce every run cited in the lab documents (about 15 minutes).
# Results are appended to results/results.tsv.
#
#   ./run_all.sh          Parts 2 and 4
#   ./run_all.sh part2    only the single-server runs
#   ./run_all.sh part4    only the strategy D runs

cd "$(dirname "$0")"
part=${1:-all}

if [ "$part" = all ] || [ "$part" = part2 ]; then
    # Part 2: single server, single server with crash, three independent servers
    bash scenarios.sh code/kv.py single
    bash scenarios.sh code/kv.py single-crash
    bash scenarios.sh code/kv.py independent
fi

if [ "$part" = all ] || [ "$part" = part4 ]; then
    # Part 4: strategy D in the five scenarios of Part 3, three runs each,
    # then a heavier load to try harder to break it
    for s in nofaults latency crash-n0 crash-n1 partition latency-high; do
        bash scenarios.sh code/d.py "$s" 3
    done
    # beyond the table: n0 is paused and comes back (memory kept)
    bash scenarios.sh code/d.py pause-n0 1
fi
