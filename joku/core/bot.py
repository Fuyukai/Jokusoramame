"""
Main bot class.
"""
import asyncio
import itertools
import logging
import sys
import time
import traceback
from collections import OrderedDict

import discord
import itsdangerous
import logbook
from discord import Message
from discord.ext import commands
from discord.ext.commands import AutoShardedBot, CheckFailure, CommandInvokeError, CommandOnCooldown, \
    MissingRequiredArgument, UserInputError, Command, Group
from kyoukai import Kyoukai
from logbook import StreamHandler
from logbook.compat import redirect_logging

from joku.core.commands import DoNotRun
from joku.core.redis import RedisAdapter
from joku.db.interface import DatabaseInterface

try:
    import yaml
except ImportError:
    import ruamel.yaml as yaml

redirect_logging()

StreamHandler(sys.stderr).push_application()


class Jokusoramame(AutoShardedBot):
    def __init__(self, config_file: str, *args, **kwargs):
        """
        Creates a new instance of the bot.

        :param config: The config to create this with.
        """
        self.config_file = config_file
        self.config = {}

        with open(self.config_file) as f:
            self.config = yaml.load(f, Loader=yaml.Loader)

        # Logging stuff
        self.logger = logbook.Logger("Jokusoramame")
        self.logger.level = logbook.INFO

        logging.root.setLevel(logging.INFO)

        # Call init.
        super().__init__(command_prefix=self.get_command_prefix, *args, **kwargs)

        # Used later on.
        self.app_id = 0
        self.owner_id = 0
        self.invite_url = ""

        self.startup_time = time.time()

        # Create our connections.
        self.database = DatabaseInterface(self)
        self.redis = RedisAdapter(self)

        # Re-assign commands and extensions.
        self.commands = OrderedDict()
        self.extensions = OrderedDict()
        self.cogs = OrderedDict()

        # Web related things.
        kyk = Kyoukai("Jokusoramame")

        @kyk.root.before_request
        async def before_request(ctx: Context):
            # add .bot property to ctx
            ctx.bot = self
            return ctx

        self.webserver = kyk

        self.signer = itsdangerous.Serializer(secret_key=self.config["webserver"]["cookie_key"],
                                              salt="jamie.anime")

        # OAuth2 class
        from joku.web.oauth import OAuth2DanceHelper
        self.oauth = OAuth2DanceHelper(bot=self)

        # Is the bot fully loaded yet?
        self.loaded = False

    # Utility functions.
    def get_member(self, id: int):
        """
        Gets a member from all members.
        """
        return discord.utils.get(self.get_all_members(), id=id)

    @staticmethod
    async def get_command_prefix(self: 'Jokusoramame', message: discord.Message):
        if self.config.get("developer_mode", False):
            # Use `jd!` prefix.
            return ["jd!", "jd::"]

        return ["j" + s for s in ["!", "?", "::", "->"]] + ["J" + s for s in ["!", "?", "::", "->"]]

    async def rotate_game_text(self):
        for i in itertools.cycle(self.config.get("game_rotation", [])):
            await self.change_presence(
                game=discord.Game(name=i), status=discord.Status.online
            )
            await asyncio.sleep(15)

    async def on_command_error(self, exception, context: 'Context'):
        """
        Handles command errors.
        """
        if isinstance(exception, CommandInvokeError):
            # Regular error.

            lines = traceback.format_exception(type(exception),
                                               exception.__cause__, exception.__cause__.__traceback__)
            self.logger.error(''.join(lines))

            if self.config.get("developer_mode", False) is False:
                await context.channel.send("\U0001f6ab This kills the bot (An error has happened "
                                           "and has been logged.)")
            else:
                await context.channel.send("```py\n{}```".format(''.join(lines)))
                return

            # Log to the error channel.
            error_channel_id = self.config.get("log_channels", {}).get("error_channel", "")
            error_channel = self.get_channel(error_channel_id)

            if not error_channel:
                self.logger.error("Could not find error channel!")
            else:
                fmt = "Server: {}\nChannel: {}\nCommand: {}\n\n```{}```".format(context.message.guild.name,
                                                                                context.message.channel.name,
                                                                                context.invoked_with,
                                                                                ''.join(lines))
                await error_channel.send(fmt)
            return

        # Switch based on isinstance.
        if isinstance(exception, CheckFailure):
            channel = context.message.channel
            await context.channel.send("\U0001f6ab Check failed: {}".format(' '.join(exception.args)))

        elif isinstance(exception, MissingRequiredArgument):
            await context.channel.send("\U0001f6ab Error: {}".format(' '.join(exception.args)))

        elif isinstance(exception, CommandOnCooldown):
            await context.channel.send("\U0001f6ab Command is on cooldown. Retry after {} "
                                       "seconds.".format(round(exception.retry_after, 1)))

        elif isinstance(exception, UserInputError):
            await context.channel.send("\U0001f6ab Error: {}".format(' '.join(exception.args)))

        elif isinstance(exception, DoNotRun):
            await context.channel.send(" ".join(exception.args))

    def reload_config_file(self):
        """
        Reloads the current config file.
        """
        with open(self.config_file) as f:
            self.config = yaml.load(f, Loader=yaml.Loader)

    async def on_connect(self):
        await self.change_presence(game=discord.Game(name="Type j!help for help!"))

    async def on_ready(self):
        # Only ever load once.
        if self.loaded is True:
            return

        self.loaded = False

        self.logger.info("Loaded Jokusoramame, logged in as {}#{}.".format(self.user.name, self.user.discriminator))
        self.logger.info("Guilds: {}".format(len(self.guilds)))
        self.logger.info("Users: {}".format(len(set(self.get_all_members()))))

        app_info = await self.application_info()
        self.app_id = app_info.id
        self.owner_id = app_info.owner.id

        self.logger.info("I am owned by {}#{} ({}).".format(app_info.owner.name, app_info.owner.discriminator,
                                                            self.owner_id))

        self.invite_url = discord.utils.oauth_url(self.app_id)

        self.logger.info("Invite link: {}".format(discord.utils.oauth_url(self.invite_url)))

        try:
            await self.database.connect(self.config.get("dsn", None))
        except Exception:
            self.logger.error("Unable to connect to PostgreSQL!")
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

        autoload = self.config.get("autoload", [])
        if "joku.cogs.core" not in autoload:
            autoload.append("joku.cogs.core")

        for cog in autoload:
            try:
                self.load_extension(cog)
            except Exception as e:
                self.logger.exception("Failed to load cog {}!".format(cog))
            else:
                self.logger.info("Loaded cog {}.".format(cog))

        self.logger.info("Loaded {} cogs.".format(len(self.cogs)))
        self.logger.info("Running with {} commands.".format(len(self.commands)))

        for name, cog in self.cogs.items():
            if hasattr(cog, "ready"):
                self.loop.create_task(cog.ready())

        self.logger.info("Booting up Kyoukai internal webserver...")
        # always add oauth2 bp
        from joku.web.oauth import bp as oauth2_bp
        self.webserver.register_blueprint(oauth2_bp)
        from joku.web.root import root as root_bp
        self.webserver.register_blueprint(root_bp)

        self.webserver.finalize()
        ws_cfg = self.config.get("webserver", {})
        try:
            await self.webserver.start(ip=ws_cfg.get("ip", "127.0.0.1"), port=ws_cfg.get("port", 4444))
        except Exception as e:
            self.logger.exception("Failed to load Kyoukai!")

        self.apply_checks()

        new_time = time.time() - self.startup_time

        self.logger.info("Bot ready in {} seconds.".format(new_time))

    def apply_checks(self):
        """
        Applies certain global checks to commands.
        """
        from joku.core.checks import md_check, non_md_check
        n = 0
        for command in self.walk_commands():
            if command.name == "help":
                continue

            # add `not_md_check` only if `md_check` is not in the command's checks
            if md_check not in command.checks and non_md_check not in command.checks:
                command.checks.append(non_md_check)
                n += 1

        self.logger.info("Applied {} new checks to commands.".format(n))

    async def on_message(self, message: Message):
        self.logger.info("Recieved message: {message.content} "
                         "from {message.author.display_name} ({message.author.name}){bot}"
                         .format(message=message, bot=" [BOT]" if message.author.bot else ""))
        self.logger.info(" On channel: #{message.channel.name}".format(message=message))

        if message.guild is not None:
            self.logger.info(" On server: {} ({})".format(message.guild.name, message.guild.id))

        # if await self.database.is_channel_ignored(message.channel, type_="commands"):
        #    return

        await super().on_message(message)

    def run(self):
        token = self.config["bot_token"]
        super().run(token)

    async def login(self, *args, **kwargs):
        token = self.config["bot_token"]
        return await super().login(token)


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
