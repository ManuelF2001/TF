#!/usr/bin/env python3

# Merge trace() events from all nodes of a Maelstrom run into one timeline,
# optionally together with client operations and nemesis (fault) events.
#
#   ./timeline.py [store/latest] [--history] [--node n1] [--event crash]
#                 [--key 0] [--process 2]
#
# Time 0 is the first client request. With --history, client operations are
# shown as p<process> (the Jepsen process in history and timeline.html) with
# the node they were sent to; nemesis events (e.g. partitions) as "nemesis".
# Client times come from jepsen.log, which has millisecond precision: within
# the same millisecond, requests are placed before node events and replies
# after them.

import argparse
import json
import re
import signal
from datetime import datetime
from pathlib import Path

parser = argparse.ArgumentParser(description='Show trace() events of a Maelstrom run')
parser.add_argument('run', nargs='?', default='store/latest', help='run directory (default: store/latest)')
parser.add_argument('--history', action='store_true', help='also show client operations and nemesis events')
parser.add_argument('--node', action='append', help='only show these nodes')
parser.add_argument('--event', action='append', help='only show these events (e.g. crash, invoke, fail)')
parser.add_argument('--key', action='append', help='only show events and operations on these keys')
parser.add_argument('--process', type=int, action='append', help='only show client operations of these processes')
args = parser.parse_args()
signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # allow piping into head or less

OP = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3})\S*\t\w+\t\[jepsen worker (\d+|nemesis)\] jepsen\.util: (.*)$')

def client_ops(run):
    # Times in jepsen.log are in the local time zone of the machine that ran
    # the test (despite the {GMT} label), as are the trace() timestamps.
    path = Path(run, 'jepsen.log')
    if not path.exists():
        return []
    text = path.read_text(errors='replace')
    nodes = re.search(r':nodes \[([^\]]*)\]', text)
    nodes = re.findall(r'"([^"]+)"', nodes.group(1)) if nodes else []
    ops = []
    nemesis_pending = None
    for line in text.splitlines():
        m = OP.match(line)
        if not m:
            continue
        stamp, worker, rest = m.groups()
        t = datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S,%f').timestamp()
        process, kind, *details = rest.split('\t')
        if worker == 'nemesis':
            # Each fault is logged when requested and again when done; show
            # only the second, which says what actually happened.
            f = details[0].lstrip(':') if details else kind
            if nemesis_pending == f:
                ops.append(dict(t=t, sort=t, who='nemesis', event=f,
                                text=' '.join(details[1:]), client=False))
                nemesis_pending = None
            else:
                nemesis_pending = f
            continue
        kind = kind.lstrip(':')
        node = nodes[int(worker) % len(nodes)] if nodes else '?'
        f, value, *error = details + ['']
        key = re.match(r'\[(-?\d+) ', value)
        ops.append(dict(t=t, sort=t if kind == 'invoke' else t + 0.000999,
                        who=f'p{process}', event=kind, node=node, process=int(process),
                        key=key.group(1) if key else None, client=True,
                        text=f"{f.lstrip(':')} {value} -> {node}" if kind == 'invoke'
                             else f"{f.lstrip(':')} {value} {' '.join(e for e in error if e)}".rstrip()))
    return ops

events = []
for log in sorted(Path(args.run, 'node-logs').glob('*.log')):
    for line in log.read_text(errors='replace').splitlines():
        if line.startswith('TRACE '):
            e = json.loads(line[len('TRACE '):])
            events.append(dict(t=e['t'], sort=e['t'], who=e['node'] or '-', event=e['event'],
                               node=e['node'], key=str(e['key']) if 'key' in e else None,
                               text=' '.join(f'{k}={json.dumps(v)}' for k, v in e.items()
                                             if k not in ('t', 'node', 'event')), client=False))

ops = client_ops(args.run)
requests = [o['t'] for o in ops if o['client'] and o['event'] == 'invoke']
if args.history:
    events += ops

if not events:
    print('no trace events found in', Path(args.run, 'node-logs'))
    raise SystemExit

events.sort(key=lambda e: e['sort'])
t0 = min(requests) if requests else events[0]['t']
for e in events:
    if args.node and e.get('node') not in args.node:
        continue
    if args.event and e['event'] not in args.event:
        continue
    if args.key and e['who'] != 'nemesis' and e['key'] not in args.key:
        continue
    if args.process and e['client'] and e['process'] not in args.process:
        continue
    print(f"{e['t'] - t0:9.3f}  {e['who']:7}  {e['event']:16} {e['text']}")
