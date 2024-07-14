# -*- coding: utf-8 -*-
#==============================================================================
# Name:         pubsub
# Purpose:      Simple publish & subscribe in pure python
# Author:       Zhen Wang
# Created:      23 Oct 2012
# Licence:      MIT License
#==============================================================================

from six.moves.queue import Queue as queue, Empty
from threading import Lock as lock
from functools import partial


MAX_QUEUE = 100
MAX_ID = 2 ** 31
PUBLISH_ID = True

channels = {}
count = {}

channels_lock = lock()
count_lock = lock()


class UnsubscribeException(Exception):
    pass


def subscribe(channel):
    if not channel:
        raise ValueError('channel')

    if channel not in channels:
        channels_lock.acquire()
        # Need to check again
        if channel not in channels:
            channels[channel] = []
        channels_lock.release()

    msg_q = queue()
    channels[channel].append(msg_q)

    msg_q.listen = partial(listen, msg_q)
    msg_q.unsubscribe = partial(unsubscribe, channel, msg_q)
    msg_q.name = channel
    return msg_q


def unsubscribe(channel, msg_q):
    if not channel:
        raise ValueError('channel')
    if not msg_q:
        raise ValueError('msg_q')
    try:
        channels[channel].remove(msg_q)
    except ValueError:
        pass


def listen(msg_q, block=True, timeout=None):
    while True:
        try:
            data = msg_q.get(block=block, timeout=timeout)
        except Empty:
            return
        if data is None:
            raise UnsubscribeException()
        yield data


def publish(channel, data):
    if not channel:
        raise ValueError('channel')
    if not data:
        raise ValueError('data')

    if channel not in channels:
        channels_lock.acquire()
        # Need to check again
        if channel not in channels:
            channels[channel] = []
        channels_lock.release()

    # Update message counts
    if PUBLISH_ID:
        count_lock.acquire()
        if channel not in count:
            count[channel] = 0
        else:
            count[channel] = (count[channel] + 1) % MAX_ID
        count_lock.release()
    else:
        count[channel] = 0

    # ID of current message
    _id = count[channel]

    # Push to all subscribers in channel
    for q in channels[channel]:
        # Remove queues that are not being consumed
        if q.qsize() > MAX_QUEUE:
            # Send termination msg and unsub
            q.put(None, block=False)
            unsubscribe(channel, q)
            continue

        q.put({'data': data, 'id': _id}, block=False)
