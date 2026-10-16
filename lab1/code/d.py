#!/usr/bin/env python3

# Lab 1, Parts 3-4: strategy D, "primary for everything".
#
# Every client request (read, write, cas) is forwarded to a fixed primary,
# n0. The primary executes it on its copy, sends the resulting value of
# the key to all other servers (fire and forget: it does not wait for
# acknowledgements) and replies. The server that received the request
# relays the primary's reply to the client.
#
# Decisions for the details the strategy leaves open:
#   - what is sent: the new value of the key (state), not the operation;
#     reads and failed cas change nothing, so they send no update.
#   - an update is applied on arrival by overwriting the key; there is no
#     acknowledgement and no ordering between updates.
#   - cas is executed only at the primary, like everything else.
#   - a backup never answers from its own copy and has no timeout: if the
#     primary does not answer, the client's request is never answered.
# There is no failover: if n0 stops, no server can complete operations.

import logging
from ms import send, reply, rpc, run, trace

logging.getLogger().setLevel(logging.DEBUG)

PRIMARY = 'n0'
store = {}          # key -> value (on the primary: the authoritative copy)

def handle(msg):
    global node_id, node_ids
    body = msg.body

    if body.type == 'init':
        node_id = body.node_id
        node_ids = body.node_ids
        logging.info('node %s initialized', node_id)
        reply(msg, type='init_ok')

    elif body.type in ('read', 'write', 'cas'):
        if node_id == PRIMARY:
            execute(msg)
        else:
            forward(msg)

    elif body.type == 'update':
        # Sent by the primary: overwrite our copy with the new value.
        store[body.key] = body.value
        trace('apply', key=body.key, value=body.value)

    else:
        logging.warning('unknown message type %s', body.type)

def forward(msg):
    # Backup: send the same request to the primary, and relay its reply to
    # the client when (if) it arrives. The handler returns immediately.
    request = {k: v for k, v in vars(msg.body).items() if k != 'msg_id'}
    trace('forward', key=msg.body.key, op=msg.body.type, client=msg.src)

    def relay(response):
        result = {k: v for k, v in vars(response.body).items()
                  if k not in ('msg_id', 'in_reply_to')}
        trace('relay', key=msg.body.key, op=msg.body.type, client=msg.src,
              result=result['type'])
        reply(msg, **result)

    rpc(node_id, PRIMARY, relay, **request)

def execute(msg):
    # Primary: execute on the authoritative copy, propagate, reply.
    # msg.src is either a client (request sent directly to n0) or a backup
    # that forwarded it; the reply goes back to whoever sent it.
    body = msg.body
    key = body.key

    if body.type == 'read':
        if key in store:
            trace('execute', key=key, op='read', value=store[key], src=msg.src)
            reply(msg, type='read_ok', value=store[key])
        else:
            trace('execute', key=key, op='read', value=None, src=msg.src)
            reply(msg, type='error', code=20, text='key does not exist')

    elif body.type == 'write':
        store[key] = body.value
        trace('execute', key=key, op='write', value=body.value, src=msg.src)
        propagate(key)
        reply(msg, type='write_ok')

    elif body.type == 'cas':
        expected = getattr(body, 'from')     # 'from' is a Python keyword
        if key not in store:
            trace('execute', key=key, op='cas', result='missing', src=msg.src)
            reply(msg, type='error', code=20, text='key does not exist')
        elif store[key] != expected:
            trace('execute', key=key, op='cas', result='mismatch', src=msg.src)
            reply(msg, type='error', code=22,
                  text=f'expected {expected}, found {store[key]}')
        else:
            store[key] = body.to
            trace('execute', key=key, op='cas', value=body.to, src=msg.src)
            propagate(key)
            reply(msg, type='cas_ok')

def propagate(key):
    for dest in node_ids:
        if dest != node_id:
            send(node_id, dest, type='update', key=key, value=store[key])
    trace('propagate', key=key, value=store[key])

run(handle)
