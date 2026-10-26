# 6 · The scripts, line by line

Four shell scripts and one Python tool are involved in running and reading
the tests:

| file | written by | purpose |
|---|---|---|
| `../../env.sh` | us (setup) | put Java 17 and gnuplot on the PATH |
| `../../kit/run.sh` | course kit | run Maelstrom with the course defaults |
| `scenarios.sh` | us | run one named scenario N times and record the result |
| `run_all.sh` | us | rerun every scenario cited in the documents |
| `../../kit/timeline.py` | course kit | merge trace events + client operations into one timeline |

---

## 1. `env.sh`

```bash
export JAVA_HOME="$HOME/.local/opt/jdk-17.0.20.1+1-jre"
export PATH="$JAVA_HOME/bin:$HOME/.local/bin:$PATH"
```

The machine has no passwordless `sudo`, so Java and gnuplot were unpacked
into the home directory instead of installed with `apt`.

- `export JAVA_HOME=…`: where Java lives; Maelstrom's launcher uses it.
- `export PATH=…:$PATH`: put `java` and `~/.local/bin` (where the
  `gnuplot` wrapper and `tectonic` are) **in front** of the existing PATH,
  so these are found first.
- `export` makes the variables visible to programs started from this shell.

It must be **sourced** (`source ../env.sh`), not executed. Executing would
run it in a child shell whose variables disappear when it ends. Sourcing
runs it in the current shell.

---

## 2. `kit/run.sh` (course kit, unmodified)

```bash
#!/usr/bin/env bash
```
Run with bash.

```bash
DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
```

The absolute path of the directory containing `run.sh`, wherever you call it
from. `${BASH_SOURCE[0]}` is the script's path, `dirname` takes its
directory, and `cd … && pwd` turns that into an absolute path. `--` means
"no more options" (protects against paths starting with `-`). `&> /dev/null`
hides any `cd` output.

```bash
MAELSTROM=${MAELSTROM:-$DIR/../maelstrom/maelstrom}
```

`${VAR:-default}`: use `$MAELSTROM` if set, otherwise the default. That
default is why `kit/` and `maelstrom/` must sit side by side.

```bash
if [ $# -lt 2 ]; then
    echo "usage: $0 <workload> <program.py> [maelstrom options]" >&2
    exit 1
fi
```

`$#` is the number of arguments. Fewer than 2 prints usage to stderr
(`>&2`) and fails.

```bash
workload=$1
program=$2
shift 2
```

Save the first two arguments, then `shift 2` removes them, so `"$@"` now
holds only the extra options (`--latency 50 --rate 50`, …).

```bash
chmod +x "$program"
```

Make the node program executable. Maelstrom runs it directly, relying on
the shebang line.

```bash
exec "$MAELSTROM" test -w "$workload" --bin "$program" \
    --node-count 3 --time-limit 20 --rate 10 --concurrency 2n "$@"
```

- `exec`: *replace* this shell with Maelstrom (no leftover bash process;
  Maelstrom's exit code becomes the script's).
- The defaults come **before** `"$@"`, so a later `--node-count 1` or
  `--rate 50` overrides them.
- `"$@"` (quoted) passes each extra argument unchanged.

Meaning of each option: `02-maelstrom.md` §4.

---

## 3. `scenarios.sh` (ours)

Usage: `bash scenarios.sh code/d.py partition 3`.

```bash
#!/usr/bin/env bash
```

```bash
cd "$(dirname "$0")"
```

Go to the directory of the script (`lab1/`), whatever directory you called
it from. So `store/`, `results/` and the relative paths `../kit/run.sh` and
`code/d.py` always refer to the right places. `$0` is the script's path.

```bash
[ -f ../env.sh ] && source ../env.sh
```

If `env.sh` exists, load it (Java on PATH). `[ -f file ]` tests "file
exists"; `&&` runs the right side only if the test succeeded.

```bash
program=$1
scenario=$2
repeats=${3:-1}
crash=""
```

Arguments: program, scenario name, number of repetitions (default 1).
`crash` starts empty (no crash).

```bash
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
```

A lookup table from scenario name to (Maelstrom options, `MS_CRASH` value).
This is the Part 3 table of the guide, written as code, plus the Part 2
scenarios and our two extra ones (`latency-high`, `pause-n0`). `;;` ends
each case. `*)` matches anything else, which is an error.
(`independent` and `nofaults` are the same command; they have different
names because one is used with `kv.py`, the other with `d.py`.)

```bash
mkdir -p results
```

Create `results/` if missing (`-p`: no error if it exists).

```bash
for i in $(seq "$repeats"); do
```

`seq 3` prints `1 2 3`, so the loop runs `repeats` times. We loop here
instead of using Maelstrom's `--test-count 3` because `store/latest` only
points to the **last** run, and we want to record every run.

```bash
    MS_CRASH="$crash" ../kit/run.sh lin-kv "$program" $opts > results/last-output.txt 2>&1
```

- `MS_CRASH="$crash" command`: set the environment variable **for this
  command only**. Maelstrom passes it on to the node processes, where
  `ms.py` reads it. An empty value means no crash (`ms.py` filters empty
  specs).
- `$opts` is **deliberately unquoted**: `"--latency 50 --rate 50"` must be
  split into four separate arguments. Quoted, it would be one strange
  argument.
- `> results/last-output.txt 2>&1`: send stdout to the file, and stderr
  (`2`) to the same place as stdout (`&1`). The whole console output of the
  run is saved.

```bash
    run=$(readlink -f store/latest)
```

`store/latest` is a symbolic link to the new run's directory.
`readlink -f` resolves it to the real path
(`…/store/lin-kv/20261016T180341.995+0100`), so the record names the actual
run and not "latest", which changes on the next run.

```bash
    edn=store/latest/results.edn
    verdict=$(tail -1 results/last-output.txt | grep -q 'Everything looks good' && echo valid || echo INVALID)
```

Take the **last line** of the output. `grep -q` prints nothing, it only
succeeds or fails. On success print `valid`, otherwise `INVALID`. This
mirrors how you'd read the console yourself.

```bash
    stat() { grep -m1 -A6 ':stats' "$edn" | grep -o ":$1 [0-9]*" | head -1 | cut -d' ' -f2; }
```

A small function that extracts one number from `results.edn`, e.g.
`stat ok-count` → `150`:

1. `grep -m1 -A6 ':stats'`: the first line containing `:stats` and the 6
   lines after it. That is the **top-level** block
   (`:count`, `:ok-count`, `:fail-count`, `:info-count`, …). The `:by-f`
   per-operation counts further down also contain `:ok-count`, and this
   window keeps them out.
2. `grep -o ":ok-count [0-9]*"`: print only the matching part,
   `:ok-count 150`.
3. `head -1`: the first match, to be safe.
4. `cut -d' ' -f2`: split on the space and take the 2nd field, `150`.

```bash
    line="$(basename "$program")\t$scenario\t$verdict\t$(stat ok-count)\t$(stat fail-count)\t$(stat info-count)\t${run#$PWD/}"
    echo -e "$line" | tee -a results/results.tsv
done
```

- Build one tab-separated line: program name (`basename` drops `code/`),
  scenario, verdict, ok, fail, info, run directory.
- `${run#$PWD/}`: remove the prefix `$PWD/` from the absolute path, leaving
  `store/lin-kv/2026…`.
- `echo -e`: interpret `\t` as real tabs.
- `tee -a`: print to the screen **and** append (`-a`) to `results.tsv`.

That gives one line per run, which is exactly what
`results/results.tsv` contains (22 lines).

---

## 4. `run_all.sh` (ours)

```bash
cd "$(dirname "$0")"
part=${1:-all}
```

Go to `lab1/`; the first argument chooses what to run (`all` by default).

```bash
if [ "$part" = all ] || [ "$part" = part2 ]; then
    bash scenarios.sh code/kv.py single
    bash scenarios.sh code/kv.py single-crash
    bash scenarios.sh code/kv.py independent
fi
```

Part 2: the three single-server runs, with `kv.py`, once each.
`bash scenarios.sh` (instead of `./scenarios.sh`) works even if the file
lost its executable bit, which happens when it's edited from Windows.

```bash
if [ "$part" = all ] || [ "$part" = part4 ]; then
    for s in nofaults latency crash-n0 crash-n1 partition latency-high; do
        bash scenarios.sh code/d.py "$s" 3
    done
    bash scenarios.sh code/d.py pause-n0 1
fi
```

Part 4: the five scenarios of the guide's table plus `latency-high`, **3
runs each** (guide Part 4.3: "repeat scenarios"), then the pause scenario
once. 6 × 3 + 1 = 19 runs of `d.py`, all valid.

---

## 5. `kit/timeline.py` (course kit), block by block

`timeline.py` produces the merged timelines quoted throughout our docs:

```
12.298  p5   invoke   write [0 4] -> n2
12.299  n2   forward  key=0 op="write" client="c9"
```

It combines two sources: our `TRACE` lines from `node-logs/*.log`, and the
client operations and nemesis events from `jepsen.log`.

### Arguments

```python
parser.add_argument('run', nargs='?', default='store/latest')   # which run directory
parser.add_argument('--history', action='store_true')           # also show client ops + nemesis
parser.add_argument('--node', action='append')                  # filters; can be repeated
parser.add_argument('--event', action='append')
parser.add_argument('--key', action='append')
parser.add_argument('--process', type=int, action='append')
args = parser.parse_args()
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
```

`nargs='?'`: the run directory is optional. `action='append'`: `--event
crash --event forward` collects a list. The `SIGPIPE` line lets you pipe
into `head` or `less` without a Python error when the pipe closes early.

### Parsing `jepsen.log`

A client line in `jepsen.log` looks like:

```
2026-10-16 18:03:44,584{GMT}	INFO	[jepsen worker 3] jepsen.util: 3	:invoke	:cas	[0 [0 3]]
```

```python
OP = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3})\S*\t\w+\t\[jepsen worker (\d+|nemesis)\] jepsen\.util: (.*)$')
```

Captures (1) the timestamp to the millisecond, (2) the worker number or
`nemesis`, (3) the rest: `process  :type  :f  value  [error]`, separated by
tabs.

```python
nodes = re.search(r':nodes \[([^\]]*)\]', text)       # ':nodes ["n0" "n1" "n2"]'
nodes = re.findall(r'"([^"]+)"', nodes.group(1))       # ['n0','n1','n2']
```

The node list, used to tell which node each worker talks to.

For each matching line:

```python
t = datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S,%f').timestamp()
process, kind, *details = rest.split('\t')
```

Convert the timestamp to seconds (the same scale as our `trace` `t`
field, since both are local time on the same machine), and split the rest.

**Nemesis lines** are logged twice: once when requested
(`:start-partition :minority-third`) and once when done, with what actually
happened (`[:isolated {"n0" #{"n2" "n1"}, …}]`). The `nemesis_pending`
variable skips the first and keeps the second.

**Client lines:**

```python
node = nodes[int(worker) % len(nodes)]
```

**Worker *w* talks to node *n(w mod 3)*.** This is where the rule "p0, p3 →
n0; p1, p4 → n1; p2, p5 → n2" comes from. (A retired process `p + 6` keeps
the same worker, so the same node.)

```python
key = re.match(r'\[(-?\d+) ', value)       # '[0 [0 3]]' → key '0'
sort = t if kind == 'invoke' else t + 0.000999
```

Extract the key (for `--key`). For **sorting**, completions (`ok`, `fail`,
`info`) are pushed to the end of their millisecond. `jepsen.log` has only
millisecond precision, while node traces have microseconds. Within the same
millisecond, a request is shown before the node events it caused, and the
reply after them.

The text shown is `f value -> node` for invokes (`write [0 4] -> n2`) and
`f value error` for completions (`write [0 4] :net-timeout`).

### Parsing node logs

```python
for log in sorted(Path(args.run, 'node-logs').glob('*.log')):
    for line in log.read_text(errors='replace').splitlines():
        if line.startswith('TRACE '):
            e = json.loads(line[len('TRACE '):])
```

Every line our `trace()` printed (`TRACE {json}`), from every node. All
fields except `t`, `node` and `event` become the text
(`key=0 op="write" client="c9"`).

### Output

```python
events.sort(key=lambda e: e['sort'])
t0 = min(requests) if requests else events[0]['t']
...
print(f"{e['t'] - t0:9.3f}  {e['who']:7}  {e['event']:16} {e['text']}")
```

Sort everything by time, set **time 0 = the first client request**, apply
the filters, and print `time  who  event  text`. `who` is the node (`n2`),
the process (`p5`), or `nemesis`.

Useful commands (from `lab1/`):

```bash
../kit/timeline.py --history                                   # last run, everything
../kit/timeline.py runs/p4-partition --history --key 0         # one key
../kit/timeline.py runs/p4-partition --history --process 5     # one client (+ all node events)
../kit/timeline.py runs/p4-crash-n0 --event crash --event forward --event relay
```

---

## 6. Not code, but part of the deliverable

- `record/record.tex`: the 2-page lab record (LaTeX). Compile with
  `cd record && tectonic record.tex` or upload it to Overleaf.
- `results/results.tsv`: the raw output of `scenarios.sh`, one line per run.
- `runs/<scenario>/`: copies of the cited `store/` runs (the guide asks to
  submit "the store/ directories of the runs it cites").
