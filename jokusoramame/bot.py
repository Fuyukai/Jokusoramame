import logbook
import traceback
from asyncqlio import DatabaseInterface
from curious import BotType, Client, EventContext, Game, Message, event
from curious.commands import CommandsManager, Context
from curious.commands.exc import CommandsError, ConditionsFailedError, ConversionFailedError, \
    MissingArgumentError, CommandInvokeError
from curious.exc import CuriousError
from curious.ext.paginator import ReactionsPaginator

from jokusoramame.db.connector import CurioAsyncpgConnector
from jokusoramame.redis import RedisInterface

logger = logbook.Logger("Jokusoramame")


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
        self.db = DatabaseInterface("postgresql://jokusoramame@127.0.0.1/jokusoramame",
                                    connector=CurioAsyncpgConnector)

        #: The redis interface.
        self.redis = RedisInterface(**self.config["redis"])

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
                await ctx.channel.messages.send(":x: An error has occurred.")
                traceback.print_exception(None, error.__cause__,
                                          error.__cause__.__traceback__)
        else:
            await ctx.channel.messages.send(f":x: {repr(error)}")

    @event("connect")
    async def on_connect(self, ctx: EventContext):
        # set the game text
        text = "[shard {}/{}] j!help".format(ctx.shard_id + 1, ctx.shard_count)
        await self.change_status(game=Game(name=text))

    @event("ready")
    async def on_ready(self, ctx: EventContext):
        logger.info(f"Shard {ctx.shard_id} loaded.")
        if self._loaded is False:
            self._loaded = True
        else:
            return

        logger.info(f"Connecting database.")
        await self.db.connect()

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
