""""""
import discord
import numpy as np
import tabulate
import time
from discord.ext import commands
from discord.ext.commands import BucketType

import rethinkdb as r

from joku.bot import Jokusoramame, Context
from joku.cogs._common import Cog
from joku.cogs.games.money.inventory import get_item_by_name, BaseItem, get_item_by_id
from joku.redis import with_redis_cooldown

BAD_RESPONSES = [
    ":fire: Your bank account went up in flames and you lost `§{}`.",
    ":grapes: You spend too much in the supermarket and you lost `§{}`.",
    ":spider: A spider arrives and you get so spooked you drop `§{}`.",
]

GOOD_RESPONSES = [
    ":money_mouth: You exploit the working class and gain `§{}`.",
    ":medal: You win first place in the Money Making Race and gain `§{}`.",
    ":slot_machine: You have a gambling addiction and win `§{}`.",
]


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

    @commands.command(pass_context=True)
    async def raffle(self, ctx: Context):
        """
        Will you win big or will you lose out?

        This can be ran once per hour.
        """
        ttl = await ctx.bot.redis.get_cooldown_expiration(ctx.message.author, "raffles")
        if ttl is not None:
            tm = time.gmtime(ttl)
            s = time.strftime("%-M", tm)
            await ctx.send(":x: You've already bought this hour's raffle ticket. "
                           "Try again in `{}` minute(s).".format(s))
            return

        currency = await ctx.bot.database.get_user_currency(ctx.message.author)
        if currency <= 0:
            choice = self.rng.randint(0, 10)
            if choice < 5:
                await ctx.send(":dragon: A debt collector came and broke your knees. You are now debt free.")
                await ctx.bot.database.update_user_currency(ctx.message.author, abs(currency) + 2)
                return True

            addiction = """Need help with a gambling addiction? We're here to help.

UK: <http://www.gamcare.org.uk/>
US: <http://www.ncpgambling.org/>
Canada: <https://www.problemgambling.ca/Pages/Home.aspx>"""
            await ctx.send(addiction)
            return False

        amount = int((300 * np.random.randn()) + 100)  # weight slightly towards positive

        await ctx.bot.database.update_user_currency(ctx.message.author, int(amount))
        if amount < 0:
            choice = self.rng.choice(BAD_RESPONSES)
        else:
            choice = self.rng.choice(GOOD_RESPONSES)

        await ctx.send(choice.format(abs(amount)))
        await ctx.bot.redis.set_bucket_with_expiration(ctx.message.author, "raffles", expiration=3600)

    @commands.group(pass_context=True, invoke_without_command=True)
    async def store(self, ctx: Context):
        """
        Store command
        """
        await ctx.channel.send("**Use `store buy` to buy things, or `store sell` to sell things.**")

    @store.command()
    @commands.cooldown(1, 5, BucketType.user)
    async def buy(self, ctx: Context, *, item: str):
        """
        Buys an item.
        """
        item = get_item_by_name(item)
        if item is None:
            await ctx.send(":x: Item does not exist.")
            return

        cls = item(ctx)  # type: BaseItem
        price = await cls.buy()

        if price is None:
            await ctx.send(":x: You do not have enough money to buy this.")
            return

        await ctx.send(":heavy_check_mark: Bought `{}` for `§{}`.".format(cls.name, price))

    @commands.command(aliases=["inv"])
    async def inventory(self, ctx: Context):
        """
        Shows your inventory.
        """
        user = await ctx.bot.database.create_or_get_user(ctx.author)
        try:
            inv = user["inventory"]
        except KeyError:
            await ctx.send(":x: You have no inventory yet.")
            return

        inventory_items = []
        for item in inv:
            id, count = item["id"], item["count"]
            item = get_item_by_id(id)

            if not item:
                # ok
                continue

            inventory_items.append((item.name, count))

        fmt = "**Inventory for {}:**\n\n".format(ctx.author.name)
        fmt += ", ".join("`{} ({})`".format(item, count) for (item, count) in inventory_items)
        await ctx.send(fmt)

    @commands.command()
    @commands.cooldown(1, 5, BucketType.user)
    async def use(self, ctx: Context, *, item: str):
        """
        Uses an item.
        """
        item = get_item_by_name(item)
        if not item:
            await ctx.send(":x: This item does not exist.")
            return

        count = await ctx.bot.database.get_user_item_count(ctx.author, item.id)
        if count <= 0:
            await ctx.send(":x: You do not have any of these.")
            return

        # make a new instance and call `.use()`
        item = item(ctx)  # type: BaseItem
        await item.use()

    @commands.group(pass_context=True, invoke_without_command=True, aliases=["money"])
    async def currency(self, ctx, *, target: discord.Member = None):
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
        users = await ctx.bot.rethinkdb.get_multiple_users(*ctx.message.guild.members, order_by=r.desc("currency"))

        base = "**Top 10 users (in this server):**\n\n```{}```"

        # Create a table using tabulate.
        headers = ["POS", "User", "Currency"]
        table = []

        for n, u in enumerate(users[:10]):
            try:
                member = ctx.message.guild.get_member(int(u["user_id"])).name
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


setup = Currency.setup
