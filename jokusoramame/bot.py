import math
import threading
import time
import traceback

import logbook
from asyncqlio import DatabaseInterface
from curious import BotType, Client, EventContext, Game, Message, Status, event
from curious.commands import CommandsManager, Context
from curious.commands.exc import CommandInvokeError, CommandRateLimited, CommandsError, ConversionFailedError, \
    MissingArgumentError
from curious.exc import CuriousError, HTTPException

from jokusoramame.db.connector import CurioAsyncpgConnector
from jokusoramame.redis import RedisInterface

logger = logbook.Logger("Jokusoramame")

specifiers = [
    (86_400, " day(s)"),
    (3600, 'h'),
    (60, 'm'),
    (1, 's')
]


class Jokusoramame(Client):
    """
    The main bot class.
    """

    def __init__(self, config: dict):
        """
        :param config: The configuration dict.
        """
        #: The config for the bot.
        self.config = config

        super().__init__(token=self.config.get("token"),
                         bot_type=BotType.BOT | BotType.ONLY_USER | BotType.NO_DMS, )

        #: The commands manager.
        command_prefix = "jd!" if self.config.get("dev_mode", False) else "j!"
        self.manager = CommandsManager(self, command_prefix=command_prefix)
        self.manager.register_events()

        #: The DB object.
        self.db = DatabaseInterface(self.config.get("db_url"),
                                    connector=CurioAsyncpgConnector)

        #: The redis interface.
        self.redis = RedisInterface(**self.config["redis"])

        #: The plotting lock. Used for pyplot compatability.
        self._plot_lock = threading.Lock()

        self._loaded = False

    @event("command_error")
    async def command_error(self, ev_ctx: EventContext, ctx: Context, error: CommandsError):
        if isinstance(error, CommandInvokeError):
            if self.config.get("dev_mode"):
                tb = traceback.format_exception(None,
                                                error.__cause__,
                                                error.__cause__.__traceback__)
                try:
                    await ctx.channel.messages.send(f"```\n{''.join(tb)}```")
                except CuriousError:
                    traceback.print_exception(None, error.__cause__,
                                              error.__cause__.__traceback__)
            else:
                if not isinstance(error.__cause__, HTTPException):
                    await ctx.channel.messages.send(":x: An error has occurred.")
                traceback.print_exception(None, error.__cause__,
                                          error.__cause__.__traceback__)
        elif isinstance(error, MissingArgumentError):
            await ctx.channel.messages.send(f":x: {repr(error)}")
        elif isinstance(error, ConversionFailedError):
            await ctx.channel.messages.send(f":x: {repr(error)}")
        elif isinstance(error, CommandRateLimited):
            seconds = int(math.ceil(error.bucket[1] - time.monotonic()))

            message = ''
            for amount, name in specifiers:
                n, seconds = divmod(seconds, amount)

                if n == 0:
                    continue

                message += f"{n}{name} "

            await ctx.channel.messages.send(f":x: The command {error.ctx.command_name} is "
                                            f"currently rate limited for {message.strip()}.")
        else:
            await ctx.channel.messages.send(f":x: {repr(error)}")

    @event("connect")
    async def on_connect(self, ctx: EventContext):
        text = f"[shard {ctx.shard_id + 1}/{ctx.shard_count}] booting..."
        await self.change_status(game=Game(name=text), status=Status.DND)

    @event("ready")
    async def on_ready(self, ctx: EventContext):
        # set the game text
        text = "[shard {}/{}] j!help".format(ctx.shard_id + 1, ctx.shard_count)
        try:
            await self.change_status(game=Game(name=text))
        except Exception:
            pass

        logger.info(f"Shard {ctx.shard_id} loaded.")
        if self._loaded is False:
            self._loaded = True
        else:
            return

        logger.info(f"Connecting database.")
        try:
            await self.db.connect()
        except ConnectionError:
            await self._kill()
            raise

        plugins = self.config.get("autoload", [])
        if "jokusoramame.plugins.core" not in plugins:
            plugins.insert(0, "jokusoramame.plugins.core")

        for plugin in plugins:
            try:
                await self.manager.load_plugins_from(plugin)
            except ModuleNotFoundError:
                logger.exception("Unable to load", plugin)
            logger.info("Loaded plugin {}.".format(plugin))

    @event("message_create")
    async def log_message(self, ctx: EventContext, message: Message):
        """
        Logs messages to stdout.
        """
        if message.content:
            logger.info(f"Received message: {message.content}")
        else:
            logger.info(f"Received message: <empty message, probably embed message>")
        logger.info(f"  From: {message.author.name} ({message.author.user.username})")
        logger.info(f"  In: {message.channel.name}")
        logger.info(f"  Guild: {message.guild.name if message.guild else 'N/A'}")

    def run(self, **kwargs):
        """
        Runs the bot.
        """
        token = self.config.get("token")
        return super().run()
