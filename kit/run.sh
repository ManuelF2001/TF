#!/usr/bin/env bash

# Run a Maelstrom test with the course's default parameters.
#
#   ./run.sh <workload> <program.py> [more Maelstrom options]
#
# Later options override the defaults, e.g.:
#   ./run.sh lin-kv kv.py --node-count 5 --nemesis partition
#   MS_CRASH="n1@5" ./run.sh lin-kv kv.py
#
# Set MAELSTROM if the maelstrom directory is not next to the kit.

DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
MAELSTROM=${MAELSTROM:-$DIR/../maelstrom/maelstrom}

if [ $# -lt 2 ]; then
    echo "usage: $0 <workload> <program.py> [maelstrom options]" >&2
    exit 1
fi

workload=$1
program=$2
shift 2

chmod +x "$program"
exec "$MAELSTROM" test -w "$workload" --bin "$program" \
    --node-count 3 --time-limit 20 --rate 10 --concurrency 2n "$@"
