"""
Debug cog.
"""
import inspect
import traceback

from discord.ext import commands
from discord.ext.commands import Context

from joku.bot import Jokusoramame
from joku.checks import is_owner


class Debug(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def eval(self, ctx, *, cmd):
        try:
            d = eval(cmd)
            if inspect.isawaitable(d):
                d = await d
        except Exception:
            await self.bot.say(''.join(traceback.format_exc()))
            return

        await self.bot.say("`" + repr(d) + "`")

    @commands.group()
    @commands.check(is_owner)
    async def debug(self):
        """
        Debug command to inspect the bot.

        Only usable by the owner.
        """

    @debug.command()
    async def reloadall(self):
        """
        Reloads all modules.
        """
        for extension in self.bot.extensions:
            self.bot.unload_extension(extension)
            self.bot.load_extension(extension)

        await self.bot.say("Reloaded all.")

    @debug.command()
    async def reload(self, module: str):
        try:
            self.bot.unload_extension(module)
            self.bot.load_extension(module)
        except Exception as e:
            await self.bot.say(e)
        else:
            await self.bot.say("Reloaded `{}`.".format(module))

    @debug.group()
    async def rdb(self):
        """
        Command group to inspect the RethinkDB status.
        """

    @rdb.command(pass_context=True)
    async def info(self, ctx):
        """
        Gets data about the RethinkDB cluster.
        """
        data = await self.bot.rethinkdb.get_info()

        tmp = {
            "server": data["server_info"]["name"],
            "server_id": data["server_info"]["id"],
            "jobs": len(data["jobs"]),
            "clients": data["stats"]["query_engine"]["client_connections"]
        }

        await self.bot.say("""**RethinkDB stats**:

**Connected to server** `{server}` (`{server_id}`).
There are `{jobs}` job(s) across `{clients}` clients.
        """.format(**tmp))


def setup(bot):
    bot.add_cog(Debug(bot))
