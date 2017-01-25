"""
RethinkDB logging adapter.

This stores events in RethinkDB as logs.
"""
import datetime
import discord
import logbook
import pytz

import rethinkdb as r


class RdbLogAdapter(object):
    def __init__(self, bot):
        self.connection = None

        self.bot = bot
        self.logger = logbook.Logger("Jokusoramame.RdbLog")

    async def _reql_safe(self, awaitable):
        """
        Runs a REQL operation, but ignoring r.RuntimeError.
        """
        try:
            res = await awaitable.run(self.connection)
        except r.ReqlRuntimeError as e:
            self.logger.warn("Failed to run REQL operation: {}".format(e))
        else:
            self.logger.info("Ran {}.".format(awaitable))
            return res

    async def _setup(self):
        """
        Creates tables, indexes, etc.
        """
        await self._reql_safe(r.db_create("joku_logs"))

        # Create table(s).
        await self._reql_safe(r.table_create("events"))

        # Create indexes.
        await self._reql_safe(r.table("events").index_create("member_id"))
        await self._reql_safe(r.table("events").index_create("message_id"))
        await self._reql_safe(r.table("events").index_create("server_id"))
        await self._reql_safe(r.table("events").index_create("channel_id"))

    async def connect(self, **connection_settings):
        """
        Connects the adapter.
        """
        self.connection = await r.connect(**connection_settings)
        await self._setup()

    async def log(self, obb: dict):
        """
        Logs an item to the database.
        """
        return
        obb["timestamp"] = datetime.datetime.now(tz=pytz.timezone("UTC"))

        i = await r.table("events").insert(obb, conflict="replace").run(self.connection)
        return i

    async def log_message(self, message: discord.Message, t: str="MESSAGE_CREATE"):
        """
        Logs a message to the database.

        Typically used on `message_create`.
        """
        obb = {
            "message_id": message.id,
            "content": message.content,
            "member_id": message.author.id,
            "member_nick": message.author.nick if isinstance(message.author, discord.Member) else None,
            "member_name": message.author.name,
            "server_id": message.server.id,
            "channel_id": message.channel.id,
            "t": t
        }

        item = await self.log(obb)
        return item

