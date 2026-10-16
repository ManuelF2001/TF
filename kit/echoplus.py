#!/usr/bin/env python3

# 'echo' workload in Python for Maelstrom showing the kit helpers:
# custom messages between nodes, rpc with callbacks, timers and trace events.

import logging
from ms import send, reply, rpc, run, every, trace

logging.getLogger().setLevel(logging.DEBUG)

def handle(msg):
    # State
    global node_id, node_ids

    # Message handlers
    if msg.body.type == 'init':
        node_id = msg.body.node_id
        node_ids = msg.body.node_ids
        logging.info('node %s initialized', node_id)

        reply(msg, type='init_ok')
        every(1.0, ping_peers)
    elif msg.body.type == 'echo':
        logging.info('echoing %s', msg.body.echo)
        trace('echo', client=msg.src)

        reply(msg, type='echo_ok', echo=msg.body.echo)
    elif msg.body.type == 'ping':
        reply(msg, type='pong')
    else:
        logging.warning('unknown message type %s', msg.body.type)

def ping_peers():
    # Never wait for replies inside a handler: register what to do when the
    # reply arrives (callback) or when it does not arrive in time (on_timeout).
    for dest in node_ids:
        if dest != node_id:
            rpc(node_id, dest,
                lambda r: trace('pong', peer=r.src),
                timeout=0.5, on_timeout=lambda d=dest: trace('no_pong', peer=d),
                type='ping')

run(handle)
