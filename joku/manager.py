import asyncio
import sys

import collections

import aiohttp
import discord
import functools
from discord.http import HTTPClient
from discord.state import ConnectionState
from logbook import Logger
from ruamel import yaml

from joku.bot import Jokusoramame


class SharedState(ConnectionState):
    """
    A modified state that shares the servers, channels etc between bot instances.
    """
    _servers = {}
    _voice_clients = {}
    _private_channels = {}

    def __init__(self, dispatch, chunker, syncer, max_messages, *, loop):
        self.loop = loop
        self.max_messages = max_messages
        self.dispatch = dispatch
        self.chunker = chunker
        self.syncer = syncer
        self.is_bot = None
        self._listeners = []
        self.clear()

    def clear(self):
        # we don't want to actually clear any of the state
        # as it's shared between clients
        # so silently discard the resetting of objects.
        self.user = None
        self.sequence = None
        self.session_id = None

        # messages, however, is not preserved.
        # why? it doesn't make sense to be shared.
        # a `messages` attribute on the manager aggregates all of the messages from the clients, however.
        self.messages = collections.deque(maxlen=self.max_messages)


class SingleLoopManager(object):
    """
    Runs the bot in a single thread, all on the same event loop.

    It is recommended to use ``uvloop`` if possible, instead of the default asyncio event loop, for increased
    performance.
    """

    def __init__(self):
        # The dict of bots.
        self.bots = {}

        self.max_shards = 0

        self.logger = Logger("Jokusoramame.LoopManager")

        self.config = {}

        self.events = collections.Counter()

    def __del__(self):
        asyncio.get_event_loop().set_exception_handler(lambda *args, **kwargs: None)

    @staticmethod
    def load_config() -> dict:
        try:
            cfg = sys.argv[1]
        except IndexError:
            cfg = "config.yml"

        with open(cfg) as f:
            return yaml.load(f)

    async def get_shard_count(self) -> int:
        """
        Gets the number of shards that the bot should use.
        """
        async with aiohttp.ClientSession() as sess:
            endpoint = HTTPClient.GATEWAY + "/bot"

            headers = {
                "Authorization": "Bot {}".format(self.config["bot_token"]),
                "User-Agent":
                    'DiscordBot (https://github.com/Rapptz/discord.py {0}) Python/{1[0]}.{1[1]} aiohttp/{2}'
                        .format(discord.__version__, sys.version_info, aiohttp.__version__)
            }
            async with sess.get(endpoint, headers=headers) as r:
                assert isinstance(r, aiohttp.ClientResponse)
                if r.status != 200:
                    raise discord.HTTPException(r, "Is your token correct?")

                return (await r.json())["shards"] + 1

    def _run_bot(self, loop: asyncio.AbstractEventLoop, shard_id: int, shard_count: int,
                 fut: asyncio.Future=None):
        """
        Starts a bot instance, and makes a task that forces it to reboot when it crashes.
        :param shard_id: The shard ID to run.
        :param shard_count: The shard count.
        """
        if loop.is_closed():
            return
        if fut is None:
            self.logger.info("Loading shard {}...".format(shard_id))
        else:
            self.logger.info("Reloading shard {}...".format(shard_id))
        bot = Jokusoramame(self.config, shard_id=shard_id, shard_count=shard_count,
                           manager=self, state=SharedState)

        task = loop.create_task(bot.start())  # type: asyncio.Task
        task.add_done_callback(functools.partial(self._run_bot, loop, shard_id, shard_count))

        bot.own_task = task

        self.bots[shard_id] = bot

        return bot

    # Start coroutines.
    async def _start(self, loop: asyncio.AbstractEventLoop):
        """
        Starts the bot in sharded mode.
        """
        shard_count = await self.get_shard_count()

        self.logger.info("Spawning {} instances of the bot.".format(shard_count))

        for x in range(0, shard_count):
            self._run_bot(loop, x, shard_count)
            # Delay each bot starting by 5 seconds.
            await asyncio.sleep(5)

    async def _start_single(self, loop: asyncio.AbstractEventLoop):
        """
        Starts a single instance of the bot.
        """
        self._run_bot(loop, 0, 1)

    def run(self):
        """
        Automatically starts all instances of the bot.
        """
        self.config = self.load_config()

        if self.config.get("use_uvloop") is True:
            # Use uvloop as the event loop.
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

        loop = asyncio.get_event_loop()

        if self.config.get("developer_mode", False) is True:
            self.logger.info("Loading single-shard instance of the bot.")
            coro = self._start_single(loop)
        else:
            coro = self._start(loop)

        # Run the coroutine forever.
        task = loop.create_task(coro)

        try:
            loop.run_until_complete(task)
            loop.run_forever()
        except KeyboardInterrupt:
            loop.stop()
        finally:
            loop.close()

    # alias methods
    def get_all_servers(self):
        for server in self.bots[0].servers:
            yield server

    def get_server(self, server_id: str):
        """
        Helper function to get a server.
        """
        # This uses bot 0 because that's always there.
        return self.bots[0].get_server(server_id)

    def get_all_members(self):
        """
        Helper function to get all members across all shards.
        """
        yield from self.bots[0].get_all_members()

    def get_all_channels(self):
        yield from self.bots[0].get_all_channels()

    def get_member(self, id: str):
        return discord.utils.get(self.get_all_members(), id=id)

    def get_channel(self, id: str):
        return discord.utils.get(self.get_all_channels(), id=id)

    @property
    def unique_member_count(self):
        return len({x.id for x in self.get_all_members()})

    def reload_config_file(self):
        self.config = self.load_config()

        for bot in self.bots.values():
            bot.config = self.config
