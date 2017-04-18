"""
Debug cog.
"""
import asyncio
import inspect
import sys
import traceback

import discord
from asyncio_extras import threadpool
from discord.ext import commands
from sqlalchemy import text
from sqlalchemy.engine import ResultProxy
from sqlalchemy.exc import ProgrammingError, DatabaseError

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import is_owner
from joku.core.utils import paginate_table


class Debug(Cog):
    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def load(self, ctx, *, cog):
        try:
            ctx.bot.load_extension(cog)
        except Exception as e:
            await ctx.channel.send(e)
        else:
            await ctx.channel.send(":heavy_check_mark: Loaded extension `{}`.".format(cog))

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def load(self, ctx, *, cog):
        try:
            ctx.bot.unload_extension(cog)
        except Exception as e:
            await ctx.channel.send(e)
        else:
            await ctx.channel.send(":heavy_check_mark: Unloaded extension.".format(cog))

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def eval(self, ctx, *, cmd):
        try:
            d = eval(cmd, {
                "asyncio": asyncio,
                "member": ctx.message.author, "message": ctx.message,
                "guild": ctx.message.guild, "channel": ctx.message.channel,
                "bot": ctx.bot, "self": self, "ctx": ctx,
                **sys.modules
            })
            if inspect.isawaitable(d):
                d = await d
        except Exception:
            f = "```{}```".format(''.join(traceback.format_exc()))
            await ctx.channel.send(f)
            return

        await ctx.channel.send("`" + repr(d) + "`")

    @commands.command()
    @commands.check(is_owner)
    async def reload(self, ctx, module: str):
        try:
            ctx.bot.unload_extension(module)
            ctx.bot.load_extension(module)
        except Exception as e:
            await ctx.channel.send(e)
        else:
            await ctx.channel.send("Reloaded `{}`.".format(module))

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def reloadall(self, ctx: Context):
        """
        Reloads all the modules for every shard.
        """
        ctx.bot.reload_config_file()

        for extension in ctx.bot.extensions.copy():
            ctx.bot.unload_extension(extension)
            try:
                ctx.bot.load_extension(extension)
            except BaseException as e:
                ctx.bot.logger.exception()
            else:
                ctx.bot.logger.info("Reloaded {}.".format(extension))

        await ctx.channel.send(":heavy_check_mark: Reloaded bot.")

    @commands.group(pass_context=False)
    @commands.check(is_owner)
    async def debug(self):
        """
        Debug command to inspect the bot.

        Only usable by the owner.
        """

    @debug.command(pass_context=True)
    async def stuck(self, ctx: Context):
        """
        Cleans stuck antispam keys.
        """
        stuck = await ctx.bot.redis.clean_stuck_antispam()
        await ctx.send(":heavy_check_mark: Cleaned `{}` stuck anti-spam keys.".format(stuck))

    @debug.command(pass_context=True)
    async def update(self, ctx: Context):
        """
        Update the bot from git.

        It is recommended to do a reloadall after this command.
        """
        await ctx.channel.send("Pulling from Git...")

        process = await asyncio.create_subprocess_exec("git", "pull",
                                                       stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)
        (stdout, stderr) = await process.communicate()

        if stdout:
            sem = discord.Embed(title="stdout", description="```\n" + stdout.decode() + "\n```")
            await ctx.channel.send(embed=sem)

        if stderr:
            rem = discord.Embed(title="stderr", description="```\n" + stderr.decode() + "\n```")
            await ctx.channel.send(embed=rem)

    @debug.command(pass_context=True)
    async def punish(self, ctx: Context, user: discord.Member):
        """
        Punishes a user.

        Sets their EXP to a very large negative number.
        """
        await ctx.bot.database.update_user_xp(user, xp=-3.4756738956329854e+307)
        await ctx.channel.send(":skull: User **{}** has been punished.".format(user))

    @debug.command(pass_context=True)
    async def resetxp(self, ctx: Context, *, user: discord.Member):
        """
        Resets a user's EXP to 0.
        """
        user_xp = await ctx.bot.database.get_user_xp(user)

        to_add = 0 - user_xp
        await ctx.bot.database.update_user_xp(user, xp=to_add)
        await ctx.channel.send(
            ":put_litter_in_its_place: User **{}** has had their XP set to 0.".format(user))

    @debug.command(pass_context=True)
    async def resetlvl(self, ctx: Context, *, user: discord.Member = None):
        """
        Resets a user's level to 0.
        """
        user = await ctx.bot.database.set_user_level(user or ctx.author, 0)
        await ctx.channel.send(":put_litter_in_its_place:")

    @debug.command(pass_context=True)
    async def sql(self, ctx: Context, *, s: str):
        """
        Executes some raw SQL.
        """
        # strip the graves
        if s.startswith("```"):
            s = s[3:]

        if s.endswith("```"):
            s = s[:-3]

        # wrpa the query in text
        t = text(s)
        # needs more indentation
        try:
            async with ctx.channel.typing():
                async with threadpool():
                    with ctx.bot.database.get_session() as sess:
                        results = sess.execute(t)  # type: ResultProxy
                        headers = results.keys()
                        all_values = results.fetchall()

                        sess.commit()

        except DatabaseError as e:
            await ctx.send("```sql\n{}```".format(e.args[0]))
            return

        if not all_values:
            await ctx.send("Query executed without results.")
            return

        tables = paginate_table(all_values, headers)
        for tbl in tables:
            await ctx.send(tbl)


def setup(bot):
    bot.add_cog(Debug(bot))
