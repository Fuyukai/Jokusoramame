"""
Debug cog.
"""
import inspect
import pprint
import traceback
import asyncio

import sys

import rethinkdb as r

import discord
from discord.ext import commands

from joku.bot import Jokusoramame, Context
from joku.checks import is_owner
from joku.cogs._common import Cog


class Debug(Cog):
    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def load(self, ctx, *, cog):
        ctx.bot.load_extension(cog)
        await ctx.bot.say(":heavy_check_mark: Loaded extension.")

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def eval(self, ctx, *, cmd):
        try:
            d = eval(cmd, {
                "r": r, "asyncio": asyncio,
                "member": ctx.message.author, "message": ctx.message,
                "server": ctx.message.server, "channel": ctx.message.channel,
                "bot": ctx.bot, "self": self, "ctx": ctx,
                **sys.modules
                })
            if inspect.isawaitable(d):
                d = await d
        except Exception:
            f = "```{}```".format(''.join(traceback.format_exc()))
            await ctx.bot.say(f)
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
    async def update(self, ctx: Context):
        """
        Update the bot from git.

        It is recommended to do a reloadall after this command.
        """
        await ctx.bot.say("Pulling from Git...")

        process = await asyncio.create_subprocess_exec("git", "pull", stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)
        (stdout, stderr) = await process.communicate()

        if stdout:
            sem = discord.Embed(title="stdout", description="```\n" + stdout.decode() + "\n```")
            await ctx.bot.say(embed=sem)

        if stderr:
            rem = discord.Embed(description="```\n" + stderr.decode() + "\n```")
            await ctx.bot.say(embed=rem)

    @debug.command(pass_context=True)
    async def reload(self, ctx, module: str):
        try:
            ctx.bot.unload_extension(module)
            ctx.bot.load_extension(module)
        except Exception as e:
            await ctx.bot.say(e)
        else:
            await ctx.bot.say("Reloaded `{}`.".format(module))

    @debug.command(pass_context=True)
    async def punish(self, ctx: Context, user: discord.User):
        """
        Punishes a user.

        Sets their EXP to a very large negative number.
        """
        await ctx.bot.rethinkdb.update_user_xp(user, xp=-3.4756738956329854e+307)
        await ctx.bot.say(":skull: User {} has been punished.".format(user))

    @debug.command(pass_context=True)
    async def resetxp(self, ctx: Context, *, user: discord.User):
        """
        Resets a user's EXP to 0.
        """
        user = await ctx.bot.rethinkdb.get_user_xp(user)

        to_add = 0 - user["xp"]
        await ctx.bot.rethinkdb.update_user_xp(user, xp=to_add)
        await ctx.bot.say(":put_litter_in_its_place: User {} has had their XP set to 0.".format(user))

    @debug.group()
    async def rdb(self):
        """
        Command group to inspect the RethinkDB status.
        """

    @rdb.command(pass_context=True)
    async def inspect(self, ctx, *, user: discord.Member):
        obb = await ctx.bot.rethinkdb.create_or_get_user(user)

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
