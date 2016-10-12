"""
Main bot class.
"""
import asyncio
import os
import shutil
import sys
import traceback

import discord
import logbook
import logging

import time
from discord.ext.commands import Bot, CommandError, CommandInvokeError, CheckFailure
from discord.ext.commands import Context
from logbook.compat import redirect_logging
from logbook import StreamHandler
from rethinkdb import ReqlDriverError

from joku.rethink import RethinkAdapter

try:
    import yaml
except ImportError:
    import ruamel.yaml as yaml

redirect_logging()

StreamHandler(sys.stderr).push_application()


class Jokusoramame(Bot):
    def __init__(self, *args, **kwargs):
        # Logging shit
        self.logger = logbook.Logger("Jokusoramame")
        self.logger.level = logbook.INFO

        logging.root.setLevel(logging.INFO)

        # Load the config
        try:
            cfg = sys.argv[1]
        except IndexError:
            cfg = "config.yml"

        # Copy the default config file.
        if not os.path.exists(cfg):
            shutil.copy("config.example.yml", cfg)

        with open(cfg) as f:
            self.config = yaml.load(f)

        if self.config.get("use_uvloop", False):
            import uvloop
            self.logger.info("Switching to uvloop.")
            policy = uvloop.EventLoopPolicy()
            self.logger.info("Created event loop policy `{}`.".format(policy))
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        else:
            self.logger.info("Using base selector event loop.")

        # Call init.
        super().__init__(command_prefix=self.get_command_prefix, *args, **kwargs)

        self.app_id = ""
        self.owner_id = ""

        self.startup_time = time.time()

        self.rethinkdb = RethinkAdapter("127.0.0.1", 28015)

    def __del__(self):
        self.loop.set_exception_handler(lambda *args, **kwargs: None)

    @staticmethod
    async def get_command_prefix(self: 'Jokusoramame', message: discord.Message):
        return "j!"

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

    async def on_ready(self):
        self.logger.info("Loaded Jokusoramame, logged in as {}#{}.".format(self.user.name, self.user.discriminator))

        app_info = await self.application_info()
        self.app_id = app_info.id
        self.owner_id = app_info.owner.id

        self.logger.info("I am owned by {}#{} ({}).".format(app_info.owner.name, app_info.owner.discriminator,
                                                            self.owner_id))
        self.logger.info("Invite link: {}".format(discord.utils.oauth_url(self.app_id)))

        try:
            await self.rethinkdb.connect()
        except ReqlDriverError:
            self.logger.error("Unable to connect to RethinkDB!")
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

        new_time = time.time() - self.startup_time

        self.logger.info("Bot ready in {} seconds.".format(new_time))

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
