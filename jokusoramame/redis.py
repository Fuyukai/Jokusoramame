"""
Redis interface.
"""
import json
import zlib

import redis
from curio.thread import async_thread
from curious import Guild, Message, User


class RedisInterface(object):
    """
    Represents an interface to the Redis server.
    """
    FLAGGED = object()

    def __init__(self, host: str = "127.0.0.1", port: int = 6379, password: str = None):
        """
        :param redis_conn: A (host, port) tuple to connect to redis on.
        """
        self.redis = redis.Redis(host=host, port=port, password=password)

    @async_thread
    def toggle_analytics(self, guild: Guild):
        """
        Toggles analytics.
        """
        key = f"analytics_enabled_{guild.id}"
        if self.redis.get(key):
            self.redis.delete(key)
            return False

        self.redis.set(key, "\x07")
        return True

    @async_thread
    def clear_member_data(self, user: User):
        """
        Clears the analytics data for a user.
        """
        self.redis.set(f"analytics_flag_{user.id}", "true")
        self.redis.delete(f"messages_{user.id}")

    @async_thread
    def add_message(self, message: Message):
        """
        Adds a message to Redis, for usage in analysis.

        :param message: The :class:`.Message` to add.
        """

        enabled = self.redis.get(f"analytics_enabled_{message.guild_id}")
        if enabled is None:
            return

        allowed = self.redis.get(f"analytics_flag_{message.author.user.id}")
        if allowed is not None:
            return

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
        allowed = self.redis.get(f"analytics_flag_{user.id}")
        if allowed is not None:
            return self.FLAGGED

        key = f"messages_{user.id}"
        results = self.redis.lrange(key, 0, 5000)
        results = [json.loads(zlib.decompress(i).decode()) for i in results]
        return results
