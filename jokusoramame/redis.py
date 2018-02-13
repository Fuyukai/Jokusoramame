"""
Redis interface.
"""
from typing import Tuple
import zlib

import json
import redis
from curio.thread import async_thread
from curious import Message, User


class RedisInterface(object):
    """
    Represents an interface to the Redis server.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6379):
        """
        :param redis_conn: A (host, port) tuple to connect to redis on.
        """
        self.redis = redis.Redis(host=host, port=port)

    @async_thread
    def add_message(self, message: Message):
        """
        Adds a message to Redis, for usage in analysis.

        :param message: The :class:`.Message` to add.
        :return:
        """
        key = f"messages_{message.author_id}"
        body = json.dumps({
            "c": message.content,
            "dt": message.created_at.timestamp(),
            "ch": message.channel_id
        })
        compressed = zlib.compress(body.encode())

        pipeline = self.redis.pipeline()
        with pipeline:
            pipeline.lpush(key, compressed)
            pipeline.ltrim(key, 0, 5000)
            pipeline.execute()

    @async_thread
    def get_messages(self, user: User):
        """
        Gets the messages for a user.
        """
        key = f"messages_{user.id}"
        l = self.redis.lrange(key, 0, 5000)
        results = [json.loads(zlib.decompress(i).decode()) for i in l]
        return results
