""""""
import discord
import tabulate
from discord.ext import commands
import rethinkdb as r

from joku.bot import Jokusoramame, Context
from joku.cogs._common import Cog
from joku.redis import with_redis_cooldown


class Currency(Cog):
    @commands.command(pass_context=True)
    @with_redis_cooldown(bucket="daily_currency")
    async def daily(self, ctx):
        """
        Gives you your daily credits.
        """
        amount = self.rng.randint(40, 60)

        await ctx.bot.rethinkdb.update_user_currency(ctx.message.author, amount)
        await ctx.channel.send(":money_with_wings: **You have earned `§{}` today.**".format(amount))

    @commands.group(pass_context=True, invoke_without_command=True)
    async def store(self, ctx: Context):
        """
        Store command
        """
        await ctx.channel.send("TODO")

    @commands.group(pass_context=True, invoke_without_command=True)
    async def currency(self, ctx, *, target: discord.User = None):
        """
        Gets the current amount of § a user has.

        If no target is provided, it will show your balance.
        """
        user = target or ctx.message.author
        if user.bot:
            await ctx.channel.send(":x: Bots cannot earn money.")
            return

        currency = await ctx.bot.rethinkdb.get_user_currency(user)
        await ctx.channel.send("User **{}** has `§{}`.".format(user, currency))

    @currency.command(pass_context=True)
    async def richest(self, ctx):
        """
        Shows the top 10 richest users in this server.
        """
        users = await ctx.bot.rethinkdb.get_multiple_users(*ctx.message.server.members, order_by=r.desc("currency"))

        base = "**Top 10 users (in this server):**\n\n```{}```"

        # Create a table using tabulate.
        headers = ["POS", "User", "Currency"]
        table = []

        for n, u in enumerate(users[:10]):
            try:
                member = ctx.message.server.get_member(u["user_id"]).name
                # Unicode and tables suck
                member = member.encode("ascii", errors="replace").decode()
            except AttributeError:
                # Prevent race condition - member leaving between command invocation and here
                continue
            # position, name, xp, level
            try:
                table.append([n + 1, member, u["currency"]])
            except KeyError:
                table.append([n + 1, member, 0])

        # Format the table.
        table = tabulate.tabulate(table, headers=headers, tablefmt="orgtbl")

        fmtted = base.format(table)

        await ctx.channel.send(fmtted)


def setup(bot):
    bot.add_cog(Currency(bot))
