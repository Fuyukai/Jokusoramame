"""
Debug cog.
"""
import inspect
import pprint
import traceback

import discord
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
            await ctx.bot.say(''.join(traceback.format_exc()))
            return

        await ctx.bot.say("`" + repr(d) + "`")

    @commands.group()
    @commands.check(is_owner)
    async def debug(self):
        """
        Debug command to inspect the bot.

        Only usable by the owner.
        """

    @debug.command(pass_context=True)
    async def reloadall(self, ctx):
        """
        Reloads all modules.
        """
        for extension in ctx.bot.extensions.copy():
            ctx.bot.unload_extension(extension)
            ctx.bot.logger.info("Reloaded {}.".format(extension))
            ctx.bot.load_extension(extension)

        await ctx.bot.say("Reloaded all.")

    @debug.command(pass_context=True)
    async def reload(self, ctx, module: str):
        try:
            ctx.bot.unload_extension(module)
            ctx.bot.load_extension(module)
        except Exception as e:
            await ctx.bot.say(e)
        else:
            await ctx.bot.say("Reloaded `{}`.".format(module))

    @debug.group()
    async def rdb(self):
        """
        Command group to inspect the RethinkDB status.
        """

    @rdb.command(pass_context=True)
    async def inspect(self, ctx, *, user: discord.Member):
        obb = await ctx.bot.rethinkdb._create_or_get_user(user)

        p = pprint.pformat(obb)
        await ctx.bot.say("```json\n{}\n```".format(p))

    @rdb.command(pass_context=True)
    async def info(self, ctx):
        """
        Gets data about the RethinkDB cluster.
        """
        data = await ctx.bot.rethinkdb.get_info()

        tmp = {
            "server": data["server_info"]["name"],
            "server_id": data["server_info"]["id"],
            "jobs": len(data["jobs"]),
            "clients": data["stats"]["query_engine"]["client_connections"]
        }

        await ctx.bot.say("""**RethinkDB stats**:

**Connected to server** `{server}` (`{server_id}`).
There are `{jobs}` job(s) across `{clients}` clients.
        """.format(**tmp))


def setup(bot):
    bot.add_cog(Debug(bot))
