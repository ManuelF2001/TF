# 2 · Maelstrom: what actually happens when you run a test

Before reading the code, you need a picture of the machine it runs in. This
file explains what `../kit/run.sh lin-kv code/d.py` does, from the moment you
press Enter until "Everything looks good!".

---

## 1. The big picture

```
                 ┌──────────────────────── Maelstrom (one Java process) ───────────────────────┐
                 │                                                                              │
                 │   clients c6..c11 ──┐                          ┌── nemesis (partitions)      │
                 │   (generator)       │   simulated network      │                             │
                 │                     ▼   (delays, drops,        ▼                             │
                 │              ┌──────────── reorders) ───────────────┐                        │
                 │              │                                      │                        │
                 │              └───┬──────────────┬──────────────┬────┘                        │
                 │                  │ stdin/stdout │ stdin/stdout │ stdin/stdout                │
                 └──────────────────┼──────────────┼──────────────┼─────────────────────────────┘
                                    ▼              ▼              ▼
                            python3 d.py     python3 d.py   python3 d.py
                               (n0)             (n1)           (n2)
                             stderr → node-logs/n0.log, n1.log, n2.log
```

- Maelstrom starts **one OS process per node**, each running our program.
- Each node talks to Maelstrom through **pipes**: it reads messages from
  **stdin** (one JSON object per line) and writes messages to **stdout**
  (one JSON object per line).
- **Every message goes through Maelstrom**, even node-to-node ones. When n1
  "sends to n0", it prints a line on its stdout. Maelstrom reads it, holds
  it for a while (latency), maybe drops it (partition), and then writes it
  to n0's stdin. This is how Maelstrom simulates an unreliable network.
- Anything the node writes to **stderr** goes to `node-logs/nX.log`. That
  is why `logging` and `trace()` write to stderr: stdout is the network, and
  writing anything else there would be read as a (broken) message.
- **Clients live inside Maelstrom.** They are not separate programs.

---

## 2. The lifecycle of one test

1. **Start**: Maelstrom launches n0, n1, n2.
2. **Init**: it sends each node an `init` message:

   ```json
   {"id":0,"src":"c0","dest":"n1",
    "body":{"type":"init","node_id":"n1","node_ids":["n0","n1","n2"],"msg_id":1}}
   ```

   The node must answer `init_ok` (`in_reply_to: 1`). This is how a node
   learns **its own name** and **the names of all nodes**. Nothing in the
   program hard-codes "I am n1".
3. **Workload**: for `--time-limit 20` seconds, the clients send `read`,
   `write` and `cas` requests at about `--rate 10` per second in total.
4. **Faults** (if requested): `--nemesis partition` makes Maelstrom cut
   links between nodes at random times. `MS_CRASH` is *not* Maelstrom; it
   is done inside our node by `ms.py`.
5. **End**: Maelstrom stops sending, waits briefly, closes the nodes.
6. **Check**: it analyses the history (linearizability, stats, latency
   graphs) and prints the verdict.

---

## 3. Messages: the format

Every message is an **envelope** plus a **body**:

```json
{"id": 15, "src": "n0", "dest": "n1",
 "body": {"msg_id": 5, "type": "update", "key": 0, "value": 0}}
```

| field | who sets it | meaning |
|---|---|---|
| `id` | Maelstrom | its own internal message number (we ignore it) |
| `src` | sender | who sent it (`n0`, `c7`, …) |
| `dest` | sender | who must receive it |
| `body.type` | sender | what kind of message (`read`, `write_ok`, `update`, …) |
| `body.msg_id` | sender | number unique **per sender**; lets someone reply to it |
| `body.in_reply_to` | replier | the `msg_id` of the request being answered |
| other body fields | sender | `key`, `value`, `from`, `to`, `code`, `text`, … |

**Request/reply matching** works only through `msg_id` / `in_reply_to`.
When n1 forwards a request to n0 with `msg_id: 2`, n0's reply carries
`in_reply_to: 2`, and that is how n1 knows which pending request it answers.
`msg_id`s are **per sender**: n0's `msg_id 5` and n1's `msg_id 5` are
unrelated.

Real example from `runs/p4-nofaults/node-logs/n1.log` (a client of n1 reads
a key that doesn't exist yet):

```
received {"id":8,"src":"c7","dest":"n1","body":{"key":0,"type":"read","msg_id":1}}
TRACE    {"node": "n1", "event": "forward", "key": 0, "op": "read", "client": "c7"}
sending  {"dest": "n0", "src": "n1", "body": {"msg_id": 2, "key": 0, "type": "read"}}
received {"id":10,"src":"n0","dest":"n1","body":{"msg_id":3,"in_reply_to":2,"type":"error","code":20,"text":"key does not exist"}}
TRACE    {"node": "n1", "event": "relay", ... "client": "c7", "result": "error"}
sending  {"dest": "c7", "src": "n1", "body": {"msg_id": 3, "in_reply_to": 1, "type": "error","code": 20,"text": "key does not exist"}}
```

Follow the numbers:

- c7's request has `msg_id 1`.
- n1 forwards it with **its own** `msg_id 2`.
- n0's answer says `in_reply_to 2`, so n1 matches it to the forward.
- n1 answers c7 with `in_reply_to 1`, which is c7's original number.

`05-d-py.md` explains which line of code does each step.

---

## 4. The options in `run.sh`

`kit/run.sh` always runs:

```
maelstrom test -w lin-kv --bin <program> \
    --node-count 3 --time-limit 20 --rate 10 --concurrency 2n  <your extra options>
```

| option | meaning | effect in our runs |
|---|---|---|
| `-w lin-kv` | workload: linearizable key-value | clients send read/write/cas; checker = linearizability |
| `--bin` | the node program | `code/d.py` |
| `--node-count 3` | number of servers | n0, n1, n2 (Part 2 overrides with 1) |
| `--time-limit 20` | seconds of workload | ~20 s of requests |
| `--rate 10` | requests per second, all clients together | ~200 ops/run; `--rate 50` → ~1000 |
| `--concurrency 2n` | number of client processes = 2 × nodes | 6 processes for 3 nodes |
| `--latency 50` | extra delay in ms on messages | observed: only server↔server messages are slowed |
| `--nemesis partition` | random network partitions between nodes | clients are never cut off from their own node |

Later options override earlier ones, so `--node-count 1` wins over the
default 3.

---

## 5. Who is who: nodes, processes, client ids

There are three kinds of names, and mixing them up is the most common
confusion when reading results.

| name | example | what it is | where you see it |
|---|---|---|---|
| **node** | `n0` | one of our servers | everywhere |
| **process** | `p3` / `3` | a *logical* client in the history | `history.txt`, `timeline.html`, `linear.svg`, `timeline.py --history` |
| **client id** | `c6` | the *network* name of a client connection | `msg.src` in our code, `messages.svg`, our trace `client=` field |

Rules:

- With 6 processes and 3 nodes, process `p` always talks to node
  `n(p mod 3)`: p0, p3 → n0; p1, p4 → n1; p2, p5 → n2.
- Each process sends **one request at a time** and waits for its answer
  (or timeout) before the next.
- **Client timeout: 1 second** (observed in our runs). No answer within 1 s
  means a timed-out `read` becomes `fail`, and a timed-out `write`/`cas`
  becomes `info`.
- After an `info`, the process is **retired** and replaced by process
  `p + 6` on the same node (p5 → p11 → p17 …), with a new client id.
- Process numbers and client ids don't match. To connect them, use
  `timeline.py --history`: an `invoke` by `p3 -> n0` is followed by the
  node's trace event naming the client id (`client="c6"`).

---

## 6. What the clients send

The `lin-kv` generator picks random operations on a small set of keys
(often just key 0 in a 20 s run) with small values (0–4):

```
read  [0 nil]          read key 0
write [0 3]            write 3 to key 0
cas   [0 [4 1]]        cas key 0 from 4 to 1
```

Values are small on purpose: it makes `cas` succeed sometimes and fail
sometimes, and it makes stale reads easy to detect.

Because values are random, many `cas` operations fail with error 22, and
early reads fail with error 20. That is why every run has a large `fail`
count even with no faults. Those are **correct answers**, not errors of our
store.

---

## 7. The output files (`store/latest/`)

`store/latest` is a link to the newest run directory
`store/lin-kv/<date-time>/`. Our `runs/<scenario>/` folders are copies.

| file | content | use it to… |
|---|---|---|
| `results.edn` | the checker's verdict and statistics | get valid?/ok/fail/info |
| `history.txt` | every invoke and completion, one per line | see exactly what clients saw |
| `history.edn` | same, in EDN with times | input to tools |
| `jepsen.log` | full Maelstrom log, incl. nemesis events | see when partitions happened |
| `timeline.html` | operations per process drawn as bars on a time axis (open in a browser) | see concurrency, timeouts |
| `independent/<key>/linear.svg` | **only if invalid**: smallest non-linearizable piece | explain the anomaly |
| `independent/<key>/results.edn` | verdict for that key | |
| `messages.svg` | Lamport diagram of *every* message | see forwards/updates/replies |
| `latency-raw.png`, `latency-quantiles.png` | latency per operation over time | see the 2-hop cost of D |
| `rate.png` | throughput over time | see availability drop after a crash |
| `node-logs/nX.log` | each node's stderr: `received`/`sending` lines and our `TRACE` lines | see what a node did |
| `net-journal/` | Maelstrom's binary network record | (not used directly) |
| `test.jepsen` | serialized test | (not used directly) |

### `history.txt` format

```
3	:invoke	:cas	[0 [4 1]]
3	:fail	:cas	[0 [4 1]]	[:key-does-not-exist key does not exist]
3	:invoke	:write	[0 0]
3	:ok	:write	[0 0]
0	:invoke	:read	[0 nil]
0	:ok	:read	[0 0]
```

Columns: process, type (`:invoke`, `:ok`, `:fail`, `:info`), function,
`[key argument]`, error. For a read, the argument is `nil` at invoke and
the value read at `:ok`.

### `results.edn`, annotated (real file from `runs/p4-nofaults`)

```clojure
{:perf {... :valid? true},              ; latency/rate graphs were drawn
 :timeline {:valid? true},              ; timeline.html was drawn
 :exceptions {:valid? true},            ; no node threw exceptions
 :stats {:valid? true,
         :count 209,                    ; operations in total
         :ok-count 150,                 ; completed successfully
         :fail-count 59,                ; definite errors (20, 22, timed-out reads)
         :info-count 0,                 ; unknown outcome
         :by-f {:cas   {:count 71, :ok-count 14, :fail-count 57, ...},   ; most cas mismatch
                :read  {:count 94, :ok-count 92, :fail-count 2,  ...},   ; 2 reads before any write
                :write {:count 44, :ok-count 44, :fail-count 0,  ...}}}, ; writes always succeed
 :availability {:valid? true, :ok-fraction 0.71770334},  ; 150 / 209
 :net {:all     {:msg-count 658, :msgs-per-op 3.15},
       :clients {:msg-count 424},       ; 209 requests + their replies (~2 per op)
       :servers {:msg-count 234, :msgs-per-op 1.12}},  ; forwards + replies + updates
 :workload {:valid? true,
            :results {0 {:linearizable {:valid? true,  ; <-- THE verdict for key 0
                          :configs ({:model #knossos.model.CASRegister{:value 1}, ...}),
                          :final-paths ()}}},          ; empty: no contradiction found
            :failures []},             ; keys that failed: none
 :valid? true}                         ; <-- overall verdict
```

Things to notice:

- `:ok-fraction` is **not** "the run was 72% correct". It is the fraction
  of operations that completed with `ok`. Even with no faults it is below 1,
  because cas mismatches and missing keys count as `fail`.
- The 234 server-to-server messages can be counted exactly from the node
  logs: 59 forwarded requests (33 from n1, 26 from n2) + 59 replies from n0
  + 116 updates (58 successful writes/cas × 2 backups) = 234. In this run
  n0's own clients issued most operations (150 of 209), so most requests
  needed no forwarding.
- `:configs … {:value 1}` is Knossos's simulated register at the end: key 0
  last held 1.
- The overall `:valid?` is false if **any** checker part fails.

### The final lines of the console

```
Everything looks good! ヽ(‘ー`)ノ      → :valid? true
Analysis invalid! (ﾉಥ益ಥ）ﾉ ┻━┻       → :valid? false
```

`scenarios.sh` reads exactly this last line to decide `valid` / `INVALID`.

---

## 8. Where `ms.py` and `MS_CRASH` fit in

Maelstrom 0.2.4 can partition the network, but it has no built-in "crash
node n0 at 5 s". The course kit adds that **inside each node** (`ms.py`):

- `MS_CRASH="n0@5"` is an environment variable. Maelstrom passes the
  environment to every node process.
- Each node reads it at `init`. If its own name is listed, then from 5 s on
  it **ignores every incoming message, sends nothing and runs no timers**.
- The process does **not** exit. If it did, Maelstrom would report a
  crashed binary and abort the test. Staying alive but silent looks exactly
  like a crashed machine to everyone else.

Details are in `03-ms-py.md` §6.
