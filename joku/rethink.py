"""
A RethinkDB database interface.
"""

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

    async def connect(self):
        """
        Connects the adapter.
        """
        self.connection = await r.connect(self.ip, self.port)

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

