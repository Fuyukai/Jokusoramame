"""
cancer
"""

import discord
from discord.ext import commands

from joku.bot import Jokusoramame


class Levelling(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

    @commands.command(pass_context=True, aliases=["exp"])
    async def xp(self, ctx, *, target: discord.Member=None):
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
