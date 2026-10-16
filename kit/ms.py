# Minimal support for Maelstrom node programs
#
# Basic API (unchanged from previous editions):
#   send(src, dest, **body)     send a message, returns its msg_id
#   reply(request, **body)      reply to a request
#   receiveAll()                iterate over incoming messages
#   exitOnError(fn, *args)      run fn, terminating the node on exceptions
#
# Additions:
#   run(handle)                 main loop: handle(msg) runs on a single thread
#   rpc(src, dest, callback, timeout=None, on_timeout=None, **body)
#                               send a request and call callback(reply) later
#   set_timeout(seconds, fn, *args) / every(seconds, fn, *args)
#                               run fn later (once / periodically) on the same thread
#   trace(event, **fields)      record a structured event (see timeline.py)
#
# Crash injection (Maelstrom itself only injects network partitions):
#   MS_CRASH="n1@5"             n1 crash-stops 5s after init
#   MS_CRASH="n1@5-15,n2@8"     n1 is down from 5s to 15s (pause: memory is
#                               kept, messages meanwhile are lost); n2 stops at 8s
# A crashed node stays alive for Maelstrom but receives, sends and executes nothing.

import logging
import threading
import time
from os import environ, _exit
from sys import stdin, stderr
from json import loads, dumps
from types import SimpleNamespace as sn
from concurrent.futures import ThreadPoolExecutor

msg_id = 0
node_id = None
node_ids = []

executor = ThreadPoolExecutor(max_workers=1)

_lock = threading.Lock()
_pending = {}
_t0 = None
_down = []

def send(src, dest, **body):
    return _send(src, dest, body)

def reply(request, **body):
    return send(request.dest, request.src, in_reply_to=request.body.msg_id, **body)

def rpc(src, dest, callback, timeout=None, on_timeout=None, **body):
    mid = _send(src, dest, body, callback)
    if timeout is not None:
        set_timeout(timeout, _expire, mid, on_timeout)
    return mid

def receiveAll():
    while data := stdin.readline():
        msg = loads(data, object_hook=lambda x: sn(**x))
        if getattr(msg.body, 'type', None) == 'init':
            _init(msg)
        if crashed():
            logging.debug("crashed, dropping received %s", data.strip())
            continue
        logging.debug("received %s", data.strip())
        yield msg

def exitOnError(fn, *args):
    try:
        fn(*args)
    except:
        logging.exception("fatal exception in handler")
        _exit(1)

def run(handle):
    for msg in receiveAll():
        executor.submit(exitOnError, _dispatch, handle, msg)

def set_timeout(seconds, fn, *args):
    timer = threading.Timer(seconds, lambda: executor.submit(exitOnError, _call, fn, *args))
    timer.daemon = True
    timer.start()
    return timer

def every(seconds, fn, *args):
    def tick():
        _call(fn, *args)
        set_timeout(seconds, tick)
    return set_timeout(seconds, tick)

def trace(event, **fields):
    record = dict(t=round(time.time(), 6), node=node_id, event=event, **fields)
    print("TRACE " + dumps(record, default=vars), file=stderr, flush=True)

def crashed():
    if _t0 is None:
        return False
    elapsed = time.monotonic() - _t0
    return any(start <= elapsed and (end is None or elapsed < end) for start, end in _down)

# Internals

def _send(src, dest, body, callback=None):
    global msg_id
    with _lock:
        msg_id += 1
        mid = msg_id
        data = dumps(sn(dest=dest, src=src, body=sn(msg_id=mid, **body)), default=vars)
        if crashed():
            logging.debug("crashed, dropping sent %s", data)
            return mid
        if callback is not None:
            _pending[mid] = callback
        logging.debug("sending %s", data)
        print(data, flush=True)
    return mid

def _dispatch(handle, msg):
    if crashed():
        return
    callback = _pending.pop(getattr(msg.body, 'in_reply_to', None), None)
    if callback is not None:
        callback(msg)
    else:
        handle(msg)

def _call(fn, *args):
    if not crashed():
        fn(*args)

def _expire(mid, on_timeout):
    if _pending.pop(mid, None) is not None and on_timeout is not None:
        on_timeout()

def _init(msg):
    global node_id, node_ids, _t0
    node_id = msg.body.node_id
    node_ids = msg.body.node_ids
    _t0 = time.monotonic()
    for spec in filter(None, environ.get('MS_CRASH', '').replace(' ', '').split(',')):
        node, _, times = spec.partition('@')
        if node != node_id:
            continue
        start, _, end = times.partition('-')
        start, end = float(start), (float(end) if end else None)
        _down.append((start, end))
        _at(start, lambda: trace('crash'))
        if end is not None:
            _at(end, lambda: trace('recover'))

def _at(seconds, fn):
    timer = threading.Timer(seconds, fn)
    timer.daemon = True
    timer.start()
