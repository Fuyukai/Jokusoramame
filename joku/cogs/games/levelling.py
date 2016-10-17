"""
cancer
"""
from math import floor

import discord
import rethinkdb as r
from discord.ext import commands

from joku.bot import Jokusoramame

INCREASING_FACTOR = 50

# Generate levels.
levels = []
current_factor = 50
for x in range(0, 1000):
    levels.append(current_factor)
    current_factor += INCREASING_FACTOR + (x * INCREASING_FACTOR)


def get_level_from_exp(exp: int):
    # I don't get it but ok
    if exp < 50:
        return 0
    return floor(-0.5 + ((-4375 + 100 * exp) ** 0.5) / 50)


class Levelling(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot
        self.levels = levels

    async def on_message(self, message: discord.Message):
        # Add XP, and show if they levelled up.
        if message.author.bot:
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

    @commands.command(pass_context=True)
    async def level(self, ctx, *, target: discord.Member = None):
        """
         Shows the current level for somebody.

        If no user is passed, this will show your level.
        """
        user = target or ctx.message.author
        if user.bot:
            await self.bot.say(":no_entry_sign: **Bots cannot have XP.**")
            return

        level = await self.bot.rethinkdb.get_level(user)

        await self.bot.say("User **{}** is level `{}`.".format(user.name, level))


    @commands.command(pass_context=True, aliases=["exp"])
    async def xp(self, ctx, *, target: discord.Member = None):
        """
        Shows the current XP for somebody.

        If no user is passed, this will show your XP.
        """
        user = target or ctx.message.author
        if user.bot:
            await self.bot.say(":no_entry_sign: **Bots cannot have XP.**")
            return

        exp = await self.bot.rethinkdb.get_user_xp(user)

        await self.bot.say("User **{}** has `{}` XP.".format(user.name, exp))


def setup(bot: Jokusoramame):
    bot.add_cog(Levelling(bot))
