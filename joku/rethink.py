"""
A RethinkDB database interface.
"""
import discord
import logbook
import rethinkdb as r

r.set_loop_type("asyncio")


class RethinkAdapter(object):
    """
    An adapter to RethinkDB.
    """

    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port

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

    async def connect(self):
        """
        Connects the adapter.
        """
        self.connection = await r.connect(self.ip, self.port, db="jokusoramame")
        await self._setup()

    async def get_info(self):
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

    async def set_setting(self, server: discord.Server, setting_name: str, value: str):
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

        d = await r.table("settings")\
            .insert(d, conflict="update")\
            .run(self.connection)

        return d

    async def get_setting(self, server: discord.Server, setting_name: str):
        """
        Gets a setting from RethinkDB.
        :param server: The server to get the setting from.
        :param setting_name: The name to retrieve.
        """
        d = await r.table("settings")\
            .get_all(server.id, index="server_id")\
            .filter({"name": setting_name})\
            .run(self.connection)

        # Only fetch one.
        # There should only be one, anyway.
        fetched = await d.fetch_next()
        if not fetched:
            return None

        i = await d.next()
        return i
