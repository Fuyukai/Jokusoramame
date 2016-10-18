""""""
import discord
from discord.ext import commands

from joku.bot import Jokusoramame
from joku.redis import with_redis_cooldown


class Currency(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

    @commands.command(pass_context=True)
    @with_redis_cooldown(bucket="daily_currency")
    async def daily(self, ctx):
        """
        Gives you your daily credits.
        """
        await self.bot.rethinkdb.update_user_currency(ctx.message.author, 50)
        await self.bot.say(":money_with_wings: **You have been given your daily `§50`.**")

    @commands.command(pass_context=True)
    async def currency(self, ctx, *, target: discord.User=None):
        """
        Gets the current amount of § a user has.

        If no target is provided, it will show your balance.
        """
        user = target or ctx.message.author
        if user.bot:
            await self.bot.say(":x: Bots cannot earn money.")
            return

        currency = await self.bot.rethinkdb.get_user_currency(user)
        await self.bot.say("User **{}** has `§{}`.".format(user, currency))


def setup(bot):
    bot.add_cog(Currency(bot))
