"""
A redis adapter for the bot.
"""
import functools

import aioredis
import discord
import logbook
import time


class RedisAdapter(object):
    def __init__(self, bot):
        self.pool = None  # type: aioredis.RedisPool

        self.bot = bot
        self.logger = bot.logger  # type: logbook.Logger

    async def connect(self, *args, **kwargs):
        """
        Connects the redis pool.
        """
        # Remove the loop argument, as we want to use the bot's loop instead.
        kwargs.pop("loop", None)

        self.pool = await aioredis.create_pool(*args, **kwargs, loop=self.bot.loop)
        return self.pool

    def get_redis(self) -> aioredis.Redis:
        """
        Gets a new connection from the pool.
        """
        return self.pool.get()

    async def prevent_spam(self, user: discord.User):
        """
        Prevents spam by only counting 15 messages per second.
        """
        b = "antispam:{}".format(user.id)

        async with self.get_redis() as redis:
            assert isinstance(redis, aioredis.Redis)

            # Check if it exists.
            if not (await redis.exists(b)):
                # Just LPUSH and EXPIRE the key.
                await redis.lpush(b, b"A")
                await redis.expire(b, 60)
                return True

            # Since it does exist, check the length.
            l_len = await redis.llen(b)

            if l_len >= 15:
                # Too much spam, return False.
                return False

            # Add 1 to it and return True.
            # Each b"A" represents a message sent.
            # If it's 15 b"A"s in the list, !
            # They've spammed too much and don't get to get XP anymore.
            await redis.lpush(b, b"A")
            return True

    async def ttl(self, key: str):
        async with self.get_redis() as redis:
            return await redis.ttl(key)

    async def get_cooldown_expiration(self, user: discord.User, bucket: str):
        built_field = "exp:{}:{}".format(user.id, bucket).encode()

        ttl = await self.ttl(built_field)
        if ttl < 0:
            return None

        return ttl

    async def set_bucket_with_expiration(self, user: discord.User, bucket: str, expiration: int):
        """
        Sets something with expiration.
        """
        async with self.get_redis() as redis:
            assert isinstance(redis, aioredis.Redis)

            # The field used for marking a expirational field is b'AAA'.
            # The key used is `exp:user_id:bucket`.
            built_field = "exp:{}:{}".format(user.id, bucket).encode()
            await redis.set(built_field, b'AAA', expire=expiration)

    async def is_on_cooldown(self, user: discord.User, bucket: str):
        """
        Checks if a command is on cooldown.
        """
        async with self.get_redis() as redis:
            assert isinstance(redis, aioredis.Redis)

            built_field = "exp:{}:{}".format(user.id, bucket).encode()
            got = await redis.get(built_field)

            return not got != b'AAA'

    async def set_daily_expiration(self, user: discord.User, bucket: str):
        """
        Sets a daily action to expire.
        """
        await self.set_bucket_with_expiration(user, bucket, expiration=86400)


def with_redis_cooldown(bucket: str, type_="DAILY"):
    """
    Decorator around a command that uses Redis for the cooldowns.
    """

    def _wrapper_inner(func):
        @functools.wraps(func)
        async def _redis_inner(self, ctx, *args, **kwargs):
            user = ctx.message.author
            on_cooldown = await ctx.bot.redis.is_on_cooldown(user, bucket)

            if on_cooldown:
                ttl = await ctx.bot.redis.get_cooldown_expiration(user, bucket)
                t = time.strftime('%-H hour(s) %-M minutes', time.gmtime(ttl))
                await ctx.send(":x: You can run this command again in `{}`.".format(t))
                return

            # Await the inner function.
            f = await func(self, ctx, *args, **kwargs)
            if f is False:
                return

            # It's not on cooldown, so set cooldown.
            if type_ == "DAILY":
                await ctx.bot.redis.set_daily_expiration(user, bucket)
            elif type_ == "HOURLY":
                await ctx.bot.redis.set_bucket_with_expiration(user, bucket, expiration=3600)

            return f

        return _redis_inner

    return _wrapper_inner
