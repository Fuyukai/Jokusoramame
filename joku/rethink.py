"""
A RethinkDB database interface.
"""
import datetime
import random

import discord
import logbook
import rethinkdb as r
import pytz

r.set_loop_type("asyncio")


class RethinkAdapter(object):
    """
    An adapter to RethinkDB.
    """

    def __init__(self):
        self.connection = None

        self.logger = logbook.Logger("Jokusoramame")

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
        Ugh.
        """
        # Make the DB.
        await self._reql_safe(r.db_create("jokusoramame"))
        # Make the tables.
        await self._reql_safe(r.table_create("settings"))
        await self._reql_safe(r.table_create("users"))
        await self._reql_safe(r.table_create("tags"))

        # Create indexes.
        await self._reql_safe(r.table("settings").index_create("server_id"))
        await self._reql_safe(r.table("users").index_create("user_id"))
        await self._reql_safe(r.table("tags").index_create("server_id"))
        await self._reql_safe(r.table("tags").index_create("name"))

    async def connect(self, **connection_settings):
        """
        Connects the adapter.
        """
        self.connection = await r.connect(**connection_settings)
        await self._setup()

    async def _create_or_get_user(self, user: discord.User) -> dict:
        iterator = await r.table("users").get_all(user.id, index="user_id").run(self.connection)

        exists = await iterator.fetch_next()
        if not exists:
            # Create a new user.
            return {
                "user_id": user.id,
                "xp": 0,
                "rep": 0,
            }

        else:
            # Get the next item from the iterator.
            # Hopefully, this is the right one.
            d = await iterator.next()
            return d

    async def update_user_xp(self, user: discord.User, xp=None) -> dict:
        """
        Updates the user's current experience.
        """
        user_dict = await self._create_or_get_user(user)

        # Add a random amount of exp.
        # lol rng
        if exp:
            added = exp
        else:
            added = random.randint(0, 3)

        user_dict["xp"] += added
        user_dict["last_modified"] = datetime.datetime.now(tz=pytz.timezone("UTC"))

        d = await r.table("users") \
            .insert(user_dict, conflict="update") \
            .run(self.connection)

        return d

    async def get_user_xp(self, user: discord.User) -> int:
        """
        Gets the user's current experience.
        """
        user_dict = await self._create_or_get_user(user)

        return user_dict["xp"]

    async def get_info(self) -> dict:
        """
        :return: Stats about the current cluster.
        """
        serv_info = await (await r.db("rethinkdb").table("server_config").run(self.connection)).next()
        cluster_stats = await r.db("rethinkdb").table("stats").get(["cluster"]).run(self.connection)

        jobs = []

        iterator = await r.db("rethinkdb").table("jobs").run(self.connection)

        while await iterator.fetch_next():
            data = await iterator.next()
            jobs.append(data)

        return {"server_info": serv_info, "stats": cluster_stats, "jobs": jobs}

    async def set_setting(self, server: discord.Server, setting_name: str, value: str) -> dict:
        """
        Sets a setting.
        :param server: The server to set the setting in.
        :param setting_name: The name to use.
        :param value: The value to insert.
        """
        # Try and find the ID.
        setting = await self.get_setting(server, setting_name)
        if not setting:
            d = {"server_id": server.id, "name": setting_name, "value": value}
        else:
            # Use the ID we have.
            d = {"server_id": server.id, "name": setting_name, "value": value, "id": setting["id"]}

        d = await r.table("settings") \
            .insert(d, conflict="update") \
            .run(self.connection)

        return d

    async def get_setting(self, server: discord.Server, setting_name: str) -> dict:
        """
        Gets a setting from RethinkDB.
        :param server: The server to get the setting from.
        :param setting_name: The name to retrieve.
        """
        d = await r.table("settings") \
            .get_all(server.id, index="server_id") \
            .filter({"name": setting_name}) \
            .run(self.connection)

        # Only fetch one.
        # There should only be one, anyway.
        fetched = await d.fetch_next()
        if not fetched:
            return None

        i = await d.next()
        return i
