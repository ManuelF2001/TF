#!/usr/bin/env bash

# Run Lab 1 scenarios and append one line per run to results/results.tsv:
#   program  scenario  verdict  ok  fail  info  run-directory
#
#   ./scenarios.sh <program.py> <scenario> [repeats]
#
# Scenarios (Part 3 table, plus the Part 2 runs):
#   single         --node-count 1
#   single-crash   MS_CRASH="n0@5" --node-count 1
#   independent    3 nodes (default)
#   nofaults       3 nodes, no faults
#   latency        --latency 50 --rate 50
#   latency-high   --latency 100 --rate 100
#   crash-n0       MS_CRASH="n0@5"
#   crash-n1       MS_CRASH="n1@5"
#   partition      --nemesis partition
#   pause-n0       MS_CRASH="n0@5-12" (n0 down 5-12 s, memory kept)
#
# Run from the lab1 directory (store/ is created here). Needs ../env.sh
# if Java and gnuplot are not installed system-wide.

cd "$(dirname "$0")"
[ -f ../env.sh ] && source ../env.sh

program=$1
scenario=$2
repeats=${3:-1}
crash=""
case $scenario in
    single)        opts="--node-count 1" ;;
    single-crash)  opts="--node-count 1"; crash="n0@5" ;;
    independent)   opts="" ;;
    nofaults)      opts="" ;;
    latency)       opts="--latency 50 --rate 50" ;;
    latency-high)  opts="--latency 100 --rate 100" ;;
    crash-n0)      opts=""; crash="n0@5" ;;
    crash-n1)      opts=""; crash="n1@5" ;;
    partition)     opts="--nemesis partition" ;;
    pause-n0)      opts=""; crash="n0@5-12" ;;
    *) echo "unknown scenario $scenario" >&2; exit 1 ;;
esac

mkdir -p results
for i in $(seq "$repeats"); do
    MS_CRASH="$crash" ../kit/run.sh lin-kv "$program" $opts > results/last-output.txt 2>&1
    run=$(readlink -f store/latest)
    edn=store/latest/results.edn
    verdict=$(tail -1 results/last-output.txt | grep -q 'Everything looks good' && echo valid || echo INVALID)
    stat() { grep -m1 -A6 ':stats' "$edn" | grep -o ":$1 [0-9]*" | head -1 | cut -d' ' -f2; }
    line="$(basename "$program")\t$scenario\t$verdict\t$(stat ok-count)\t$(stat fail-count)\t$(stat info-count)\t${run#$PWD/}"
    echo -e "$line" | tee -a results/results.tsv
done
