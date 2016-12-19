"""
Main bot class.
"""
import asyncio
import os
import sys
import traceback
from collections import OrderedDict
import time
import random

import discord
import logbook
import logging

from discord.ext import commands
from discord.ext.commands import Bot, CommandInvokeError, CheckFailure, MissingRequiredArgument
from discord.gateway import DiscordWebSocket, ReconnectWebSocket, ResumeWebSocket
from discord.state import ConnectionState
from logbook.compat import redirect_logging
from logbook import StreamHandler

from joku.rdblog import RdbLogAdapter
from joku.utils import paginate_large_message
from rethinkdb import ReqlDriverError

from joku.redis import RedisAdapter
from joku.rethink import RethinkAdapter

from joku import manager

try:
    import yaml
except ImportError:
    import ruamel.yaml as yaml

redirect_logging()

StreamHandler(sys.stderr).push_application()


class Jokusoramame(Bot):
    def __init__(self, config: dict, *args, **kwargs):
        """
        Creates a new instance of the bot.

        :param config: The config to create this with.

        :param manager: The bot manager to use.
        :param state: The type of state to use. This can either be the vanilla ConnectionState, or a modified subclass.
        """

        # Get the shard ID.
        shard_id = kwargs.get("shard_id", 0)

        self.manager = kwargs.get("manager")  # type: manager.SingleLoopManager

        self.config = config

        # Logging stuff
        self.logger = logbook.Logger("Jokusoramame:Shard-{}".format(shard_id))
        self.logger.level = logbook.INFO

        logging.root.setLevel(logging.INFO)

        # Call init.
        super().__init__(command_prefix=self.get_command_prefix, *args, **kwargs)

        # Override ConnectionState.
        self.connection = kwargs.get("state", ConnectionState) \
            (self.dispatch, self.request_offline_members,
             self._syncer, self.connection.max_messages, loop=self.loop)

        self.app_id = ""
        self.owner_id = ""

        self.startup_time = time.time()

        self.rethinkdb = RethinkAdapter(self)
        self.rdblog = RdbLogAdapter(self)

        self.redis = RedisAdapter(self)

        # Re-assign commands and extensions.
        self.commands = OrderedDict()
        self.extensions = OrderedDict()
        self.cogs = OrderedDict()

        self._rotator_task = None  # type: asyncio.Task
        self._avatar_rotator = None  # type: asyncio.Task

        # Our own task.
        # We can use this to kill ourselves by running `self.own_task.cancel()`.
        self.own_task = None  # type: asyncio.Task

    # Utility functions.
    def get_member(self, id: str):
        """
        Gets a member from all members.
        """
        return discord.utils.get(self.get_all_members(), id=id)

    @staticmethod
    async def get_command_prefix(self: 'Jokusoramame', message: discord.Message):
        if self.config.get("developer_mode", False):
            # Use `jd!` prefix.
            return "jd!"

        if message.server.id == "110373943822540800":
            # Don't conflict in dbots
            return ["j" + s for s in "?^&$}#~:"]
        return ["j" + s for s in "!?^&$}#~:"]

    async def rotate_game_text(self):
        while True:
            await self.change_presence(
                game=discord.Game(name="[Shard {}/{}] {} Servers".format(
                    self.shard_id + 1, self.shard_count, len(self.servers)
                )), status=discord.Status.online
            )
            await asyncio.sleep(60)

    async def on_command_error(self, exception, context):
        """
        Handles command errors.
        """
        if isinstance(exception, CommandInvokeError):
            # Regular error.
            await self.send_message(context.message.channel, "\U0001f6ab An error has occurred and has been logged.")
            lines = traceback.format_exception(type(exception),
                                               exception.__cause__, exception.__cause__.__traceback__)
            self.logger.error(''.join(lines))
            return

        # Switch based on isinstance.
        if isinstance(exception, CheckFailure):
            channel = context.message.channel
            await self.send_message(channel, "\U0001f6ab Check failed: {}".format(' '.join(exception.args)))

        elif isinstance(exception, MissingRequiredArgument):
            await self.send_message(context.message.channel, "\U0001f6ab Error: {}".format(' '.join(exception.args)))

    async def on_ready(self):
        self.logger.info("Loaded Jokusoramame, logged in as {}#{}.".format(self.user.name, self.user.discriminator))

        app_info = await self.application_info()
        self.app_id = app_info.id
        self.owner_id = app_info.owner.id

        self.logger.info("I am owned by {}#{} ({}).".format(app_info.owner.name, app_info.owner.discriminator,
                                                            self.owner_id))
        self.logger.info("Invite link: {}".format(discord.utils.oauth_url(self.app_id)))

        try:
            await self.rethinkdb.connect(**self.config.get("rethinkdb", {}))
            data = self.config.get("rethinkdb", {}).copy()
            data["db"] = "joku_logs"
            await self.rdblog.connect(**data)
        except ReqlDriverError:
            self.logger.error("Unable to connect to RethinkDB!")
            traceback.print_exc()
            await self.logout()
            return

        try:
            await self.redis.connect(**self.config.get("redis", {}))
        except ConnectionRefusedError:
            self.logger.error("Unable to connect to Redis!")
            traceback.print_exc()
            await self.logout()
            return

        for cog in self.config.get("autoload", []):
            try:
                self.load_extension(cog)
            except Exception as e:
                self.logger.error("Failed to load cog {}!".format(cog))
                self.logger.exception()
            else:
                self.logger.info("Loaded cog {}.".format(cog))

        for name, cog in self.cogs.items():
            if hasattr(cog, "ready"):
                self.loop.create_task(cog.ready())

        if self._rotator_task is not None:
            self._rotator_task.cancel()
            try:
                self._rotator_task.result()
            except Exception:
                self.logger.exception()

        self._rotator_task = self.loop.create_task(self.rotate_game_text())

        new_time = time.time() - self.startup_time

        self.logger.info("Bot ready in {} seconds.".format(new_time))

    async def on_message(self, message):
        self.logger.info("Recieved message: {message.content} "
                         "from {message.author.display_name} ({message.author.name}){bot}"
                         .format(message=message, bot=" [BOT]" if message.author.bot else ""))
        self.logger.info(" On channel: #{message.channel.name}".format(message=message))

        if message.server is not None:
            self.logger.info(" On server: {} ({})".format(message.server.name, message.server.id))

        # Check if an ignore rule exists for that channel.
        if self.rethinkdb.connection is None:
            return

        if await self.rethinkdb.is_channel_ignored(message.channel, type_="commands"):
            return

        await super().on_message(message)

    async def on_message_edit(self, before: discord.Message, message: discord.Message):
        await self.on_message(message)

    def run(self):
        token = self.config["bot_token"]
        super().run(token)

    async def login(self, *args, **kwargs):
        token = self.config["bot_token"]
        return await super().login(token)

    # Overrides.
    async def send_message(self, destination, content=None, *, tts=False, embed=None, use_codeblocks=False):
        """
        Sends a message, with pagination.

        This will automatically split messages over 2000 chracters.
        """
        if not content:
            return await super().send_message(destination, tts=tts, embed=embed)
        pages = paginate_large_message(content, use_codeblocks=use_codeblocks)
        messages = []
        for page in pages:
            messages.append(await super().send_message(destination, page, tts=tts, embed=embed))

        if len(messages) == 1:
            return messages[0]
        return messages

    async def connect(self):
        self.ws = await DiscordWebSocket.from_client(self)
        # Send the CHANGE_PRESCENCE to DND.
        await self.change_presence(game=discord.Game(name="Loading Jokusoramame.."),
                                   status=discord.Status.do_not_disturb)

        while not self.is_closed:
            try:
                await self.ws.poll_event()
            except (ReconnectWebSocket, ResumeWebSocket) as e:
                resume = type(e) is ResumeWebSocket
                self.logger.info('Got ' + type(e).__name__)
                self.ws = await DiscordWebSocket.from_client(self, resume=resume)
            except discord.ConnectionClosed as e:
                await self.close()
                await self.rethinkdb.connection.close()
                await self.rdblog.connection.close()
                if e.code != 1000:
                    raise

    def die(self):
        """
        Kills all tasks the bot is running.
        """
        self.loop.stop()
        all_tasks = asyncio.gather(*asyncio.Task.all_tasks(), loop=self.loop)
        all_tasks.cancel()

        # Get rid of the exceptions.
        all_tasks.exception()


class Context(commands.Context):
    def __init__(self, *args, **kwargs):
        self._bot = None
        super().__init__(*args, **kwargs)

    @property
    def bot(self) -> Jokusoramame:
        return self._bot

    @bot.setter
    def bot(self, i):
        self._bot = i
