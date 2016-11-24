"""
cancer
"""
from io import BytesIO
from math import floor, ceil

import discord
from asyncio_extras import threadpool

import rethinkdb as r
from discord.ext import commands

import matplotlib as mpl

mpl.use('Agg')

import matplotlib.pyplot as plt
import numpy as np
from numpy.polynomial import Polynomial as P

from joku.bot import Jokusoramame, Context
from joku.cogs._common import Cog
from joku.utils import paginate_table, reject_outliers

INCREASING_FACTOR = 50


def get_level_from_exp(xp: int, a: int = INCREASING_FACTOR) -> int:
    """
    Gets the level from the experience number.

    U(n) = a* (n*(n+1)  / 2), a ∈ ℝ, a > 0
    :param a: The levelling up constant.
    :param xp: The XP this user currently has.
    """
    # Make sure XP is below INCREASING_FACTOR.
    if xp < a:
        # Level 1
        return 1

    # The equation that we need to solve is (a/2)n**2 + (a/2)n - xp = 0.
    # So we get numpy to find our roots.
    ab = a / 2
    # C, B, A
    to_solve = [-xp, ab, ab]
    poly = P(to_solve)

    # Positive root + 1
    root = poly.roots()[1] + 1
    return int(floor(root))


def get_next_exp_required(xp: int, a: int = INCREASING_FACTOR):
    """
    Gets the EXP required for the next level, based on the current EXP.

    :param a: The levelling up constant.
    :param xp: The XP this user currently has.
    :return: The amount of XP required for the next level, and the current level.
    """
    # No complxes
    if xp < a:
        return 1, a - xp

    # Solve the current level.
    current_level = get_level_from_exp(xp, a)

    # Substitute in (n+1) to a* (n*(n+1)  / 2), where n == current_level
    exp_required = int(a * ((current_level + 1) * (current_level + 2) / 2))

    return current_level, exp_required - xp


class Levelling(Cog):
    async def on_message(self, message: discord.Message):
        # Add XP, and show if they levelled up.
        if message.author.bot:
            return

        # No discord bots, thanks.
        if message.server.id == "110373943822540800":
            return

        # Check the spam quotient.
        if not await self.bot.redis.prevent_spam(message.author):
            # The user said more than 15 messages in the last 60 seconds, so don't add XP.
            return

        # Check if this channel should be ignored for levelling.
        if await self.bot.rethinkdb.is_channel_ignored(message.channel, type_="levels"):
            return

        user = await self.bot.rethinkdb.update_user_xp(message.author)
        # Get the level.
        new_level = get_level_from_exp(user["xp"])

        if user.get("level", 0) < new_level:
            # todo: make this better
            user["level"] = new_level
            await r.table("users").insert(user, conflict="update").run(self.bot.rethinkdb.connection)

            await self.bot.send_message(message.channel, ":up: **{}, you are now level {}!**".format(
                message.author, new_level
            ))

    @commands.group(pass_context=True, invoke_without_command=True)
    async def level(self, ctx, *, target: discord.Member = None):
        """
        Shows the current level for somebody.

        If no user is passed, this will show your level.
        """
        user = target or ctx.message.author
        if user.bot:
            await ctx.bot.say(":no_entry_sign: **Bots cannot have XP.**")
            return

        level = await ctx.bot.rethinkdb.get_level(user)

        await ctx.bot.say("User **{}** is level `{}`.".format(user.name, level))

    @level.command(pass_context=True, aliases=["top"])
    async def leaderboard(self, ctx: Context, *, num: int = 10):
        """
        Shows the top 10 people in this server.

        This uses the global XP counter.
        """
        users = await ctx.bot.rethinkdb.get_multiple_users(*ctx.message.server.members, order_by=r.desc("xp"))

        base = "**Top {} users (in this server):**\n\n".format(num)

        # Create a table using tabulate.
        headers = ["POS", "User", "XP", "Level"]
        table = []

        for n, u in enumerate(users[:num]):
            try:
                member = ctx.message.server.get_member(u["user_id"]).name
                # Unicode and tables suck
                member = member.encode("ascii", errors="replace").decode()
            except AttributeError:
                # Prevent race condition - member leaving between command invocation and here
                continue
            # position, name, xp, level
            table.append([n + 1, member, u["xp"], u["level"]])

        # Format the table.
        pages = paginate_table(table, headers)

        await ctx.bot.say(base)
        for page in pages:
            await ctx.bot.say(page)

    @level.command(pass_context=True)
    async def plot(self, ctx: Context):
        """
        Plots the XP curve for this server.
        """
        users = await ctx.bot.rethinkdb.get_multiple_users(*ctx.message.server.members, order_by=r.desc("xp"))

        await ctx.bot.type()

        async with threadpool():
            with plt.style.context("seaborn-pastel"):
                lvls = np.array([user["level"] for user in users if user["level"] >= 0])
                lvls = reject_outliers(lvls)
                plt.hist(lvls, bins=np.arange(lvls.min(), lvls.max() + 1))

                plt.xlabel("Level")
                plt.ylabel("Frequency")
                plt.title("Level frequency for {}".format(ctx.message.server.name))

                buf = BytesIO()
                plt.savefig(buf, format="png")

                # Don't send 0-byte files
                buf.seek(0)

                # Cleanup.
                plt.clf()
                plt.cla()

        await ctx.bot.upload(buf, filename="plot.png")

    @level.command(pass_context=True)
    async def next(self, ctx, *, target: discord.Member = None):
        """
        Shows the next level for somebody.

        If no user is passed, this will show yours.
        """
        user = target or ctx.message.author
        if user.bot:
            await ctx.bot.say(":no_entry_sign: **Bots cannot have XP.**")
            return

        level = await ctx.bot.rethinkdb.get_level(user)
        xp = await ctx.bot.rethinkdb.get_user_xp(user)

        exp_required = get_next_exp_required(xp)[1]

        await ctx.bot.say("**{}** needs `{}` XP to advance to level `{}`.".format(user.name, exp_required,
                                                                                  level + 1))

    @commands.command(pass_context=True, aliases=["exp"])
    async def xp(self, ctx, *, target: discord.Member = None):
        """
        Shows the current XP for somebody.

        If no user is passed, this will show your XP.
        """
        user = target or ctx.message.author
        if user.bot:
            await ctx.bot.say(":no_entry_sign: **Bots cannot have XP.**")
            return

        exp = await ctx.bot.rethinkdb.get_user_xp(user)

        await ctx.bot.say("User **{}** has `{}` XP.".format(user.name, exp))


def setup(bot: Jokusoramame):
    bot.add_cog(Levelling(bot))
