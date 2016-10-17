""""""
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
        await self.bot.say(":money_with_wings: **You have been given your daily §50.**")


def setup(bot):
    bot.add_cog(Currency(bot))
