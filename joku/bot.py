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

from discord.ext.commands import Bot, CommandInvokeError, CheckFailure, MissingRequiredArgument
from logbook.compat import redirect_logging
from logbook import StreamHandler
from rethinkdb import ReqlDriverError

from joku.redis import RedisAdapter
from joku.rethink import RethinkAdapter
from joku import threadmanager

try:
    import yaml
except ImportError:
    import ruamel.yaml as yaml

redirect_logging()

StreamHandler(sys.stderr).push_application()


class Jokusoramame(Bot):
    def __init__(self, config: dict, *args, **kwargs):
        # Get the shard ID.
        shard_id = kwargs.get("shard_id", 0)

        self.manager = kwargs.get("manager")  # type: threadmanager.Manager

        self.config = config

        # Logging stuff
        self.logger = logbook.Logger("Jokusoramame:Shard-{}".format(shard_id))
        self.logger.level = logbook.INFO

        logging.root.setLevel(logging.INFO)

        # Call init.
        super().__init__(command_prefix=self.get_command_prefix, *args, **kwargs)

        self.app_id = ""
        self.owner_id = ""

        self.startup_time = time.time()

        self.rethinkdb = RethinkAdapter(self)

        self.redis = RedisAdapter(self)

        # Re-assign commands and extensions.
        self.commands = OrderedDict()
        self.extensions = OrderedDict()
        self.cogs = OrderedDict()

        self._rotator_task = None  # type: asyncio.Task
        self._avatar_rotator = None  # type: asyncio.Task

    def __del__(self):
        self.loop.set_exception_handler(lambda *args, **kwargs: None)

    # Utility functions.
    def get_member(self, id: str):
        """
        Gets a member from all members.
        """
        return discord.utils.get(self.get_all_members(), id=id)

    @staticmethod
    async def get_command_prefix(self: 'Jokusoramame', message: discord.Message):
        if message.server.id == "110373943822540800":
            # Don't conflict in dbots
            return ["j" + s for s in "?^&$}#~:"]
        return ["j" + s for s in "!?^&$}#~:"]

    async def rotate_game_text(self):
        while True:
            await self.change_presence(
                game=discord.Game(name="[Shard {}/{}] {} Servers".format(
                    self.shard_id + 1, self.shard_count, len(self.servers)
                ))
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
        except ReqlDriverError:
            self.logger.error("Unable to connect to RethinkDB!")
            await self.logout()
            return

        try:
            await self.redis.connect(**self.config.get("redis", {}))
        except ConnectionRefusedError:
            self.logger.error("Unable to connect to Redis!")
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

        if self._rotator_task is not None:
            self._rotator_task.cancel()
            try:
                self._rotator_task.result()
            except Exception:
                self.logger.exception()

        self._rotator_task = self.loop.create_task(self.rotate_game_text())

        if self.shard_id == 0:
            # Start the avatar rotator.
            if self._avatar_rotator is None:
                self._avatar_rotator = self.loop.create_task(self._rotate_avatar())
            else:
                try:
                    if self._avatar_rotator.done():
                        # Get the exception and kill it.
                        self._avatar_rotator.result()
                except Exception:
                    self.logger.exception()

        new_time = time.time() - self.startup_time

        self.logger.info("Bot ready in {} seconds.".format(new_time))

    async def _rotate_avatar(self):
        while True:
            # Pick a random avatar from the `avatars/` directory.
            scanned = os.scandir("avatars/")
            r = random.choice([_ for _ in scanned])
            p = r.path
            with open(p, 'rb') as f:
                data = f.read()
            # Set the avy.
            await self.edit_profile(avatar=data)

            # Sleep for 300 seconds.
            await asyncio.sleep(300)

    async def on_message(self, message):
        self.logger.info("Recieved message: {message.content} from {message.author.display_name}{bot}"
                         .format(message=message, bot=" [BOT]" if message.author.bot else ""))
        self.logger.info(" On channel: #{message.channel.name}".format(message=message))

        if message.server is not None:
            self.logger.info(" On server: {} ({})".format(message.server.name, message.server.id))

        await super().on_message(message)

    def run(self):
        token = self.config["bot_token"]
        super().run(token)

    async def login(self, *args, **kwargs):
        token = self.config["bot_token"]
        return await super().login(token)

    def die(self):
        """
        Kills all tasks the bot is running.
        """
        self.loop.stop()
        all_tasks = asyncio.gather(*asyncio.Task.all_tasks(), loop=self.loop)
        all_tasks.cancel()

        # Get rid of the exceptions.
        all_tasks.exception()
