#!/usr/bin/env python3

# Lab 1, Part 2: single-server lin-kv node.
#
# Each node keeps its own dictionary and answers every request from it.
# There is no communication between nodes: with --node-count 1 this is a
# correct (linearizable) store; with several nodes each one is an
# independent store and clients of different nodes see different values.

import logging
from ms import reply, run, trace

logging.getLogger().setLevel(logging.DEBUG)

store = {}          # key -> value

def handle(msg):
    global node_id, node_ids
    body = msg.body

    if body.type == 'init':
        node_id = body.node_id
        node_ids = body.node_ids
        logging.info('node %s initialized', node_id)
        reply(msg, type='init_ok')

    elif body.type == 'read':
        if body.key in store:
            reply(msg, type='read_ok', value=store[body.key])
        else:
            reply(msg, type='error', code=20, text='key does not exist')

    elif body.type == 'write':
        store[body.key] = body.value
        trace('write', key=body.key, value=body.value, client=msg.src)
        reply(msg, type='write_ok')

    elif body.type == 'cas':
        expected = getattr(body, 'from')     # 'from' is a Python keyword
        if body.key not in store:
            reply(msg, type='error', code=20, text='key does not exist')
        elif store[body.key] != expected:
            reply(msg, type='error', code=22,
                  text=f'expected {expected}, found {store[body.key]}')
        else:
            store[body.key] = body.to
            trace('cas', key=body.key, value=body.to, client=msg.src)
            reply(msg, type='cas_ok')

    else:
        logging.warning('unknown message type %s', body.type)

run(handle)
