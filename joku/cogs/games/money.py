""""""
import asyncio
import datetime
import time

import discord
import numpy as np
import tabulate
from asyncio_extras import threadpool
from discord.ext import commands
from sqlalchemy.orm import Session

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.redis import with_redis_cooldown
from joku.db.tables import User

BAD_RESPONSES = [
    ":fire: Your bank account went up in flames and you lost `§{}`.",
    ":grapes: You spend too much in the supermarket and you lost `§{}`.",
    ":spider: A spider arrives and you get so spooked you drop `§{}`.",
    ":hammer_pick: The revolution comes and your wealth of `§{}` is redistributed.",
    ":dragon: Ryuu ga waga teki wo kurau! (You lost `§{}`.)"
]

GOOD_RESPONSES = [
    ":money_mouth: You exploit the working class and gain `§{}`.",
    ":medal: You win first place in the Money Making Race and gain `§{}`.",
    ":slot_machine: You have a gambling addiction and win `§{}`.",
    ":gem: You find a gem and sell it for `§{}`.",
    ":u6709: Anata wa okane o eru. (You gained `§{}`.)"
]

BODY_PARTS = [
    "knees",
    "shin",
    "arms",
    "kidneys",
    "skull",
    "gluteus maximus",
]


def calculate_monetary_decay(money: int, factor: float = -0.05, hours: int = 1) -> int:
    """
    Calculates monetary decay over X hours.
    """
    return int(np.math.ceil(money * (np.math.exp(factor * hours))))


def get_next_decay(currency: int, factor: float=-0.05) -> int:
    if 0 < currency <= 1343:
        return 0

    return currency - calculate_monetary_decay(currency, factor=factor)


class Currency(Cog):
    running = False

    async def ready(self):
        if self.running is True:
            return

        self.running = True

        # Wait until the hour is up.
        try:
            now = datetime.datetime.now()
            if now.hour == 23:
                # clamp
                hour = 0
                day = now.day + 1
            else:
                hour = now.hour + 1
                day = now.day

            next = datetime.datetime(year=now.year, month=now.month, day=day,
                                     hour=hour, minute=0, second=0)
            to_wait = (next - now).total_seconds()

            while True:
                self.logger.info("Waiting {} seconds before applying next decay.".format(to_wait))
                await asyncio.sleep(to_wait)

                # decay
                total = 0
                async with threadpool():
                    with self.bot.database.get_session() as sess:
                        assert isinstance(sess, Session)

                        users = list(sess.query(User).filter((User.money < 0) | (User.money > 1343)).all())
                        for user in users:
                            decay = get_next_decay(user.money)
                            user.money -= decay
                            total += decay

                            # update the user
                            sess.merge(user)

                self.logger.info("Decayed §{}.".format(total))
                to_wait = 60 * 60  # 1 hr
        finally:
            self.running = False

    @commands.command(pass_context=True)
    @with_redis_cooldown(bucket="daily_currency")
    async def daily(self, ctx: Context):
        """
        Gives you your daily credits.
        """
        # multiply by 40 to get a good number
        amount = np.random.exponential() * 40
        # minimum of 20
        amount = max(20, int(amount))

        await ctx.bot.database.update_user_currency(ctx.message.author, amount)
        await ctx.channel.send(":money_with_wings: **You have earned `§{}` today.**".format(amount))

    @commands.command(pass_context=True)
    async def raffle(self, ctx: Context, *, price: int = 2):
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
            await ctx.send(":dragon: A debt collector came and broke your {}. "
                           "You are now debt free.".format(self.rng.choice(BODY_PARTS)))
            await ctx.bot.database.update_user_currency(ctx.message.author, abs(currency) + 2)
            return

        if price < 2:
            await ctx.send(":x: You must buy a ticket worth at least `§2`.")
            return

        if price > currency:
            await ctx.send(":x: It is unwise to gamble with money you don't have")
            return

        amount = int((price * np.random.randn()) + 100)  # weight slightly towards positive
        amount -= price

        await ctx.bot.database.update_user_currency(ctx.message.author, int(amount))
        if amount < 0:
            choice = self.rng.choice(BAD_RESPONSES)
        else:
            choice = self.rng.choice(GOOD_RESPONSES)

        await ctx.send(choice.format(abs(amount)))
        await ctx.bot.redis.set_bucket_with_expiration(ctx.message.author, "raffles", expiration=3600)

    @commands.group(pass_context=True, invoke_without_command=True, aliases=["money"])
    async def currency(self, ctx: Context, *, target: discord.Member = None):
        """
        Gets the current amount of § a user has.

        If no target is provided, it will show your balance.
        """
        user = target or ctx.message.author
        if user.bot:
            await ctx.channel.send(":x: Bots cannot earn money.")
            return

        currency = await ctx.bot.database.get_user_currency(user)

        if ctx.channel.permissions_for(ctx.guild.me).embed_links:
            day = self.rng.randint(1, 31)
            hour, minute, second = self.rng.randint(0, 23), self.rng.randint(0, 59), self.rng.randint(0, 59)

            ts = datetime.datetime(year=2008, month=7, day=day, hour=hour, minute=minute, second=second)

            em = discord.Embed(title="First National Bank of Joku")
            em.description = "Your tax is the amount of money you gain or lose **every hour**.\n" \
                             "You do not lose money if you are you below the Basic Tax Bracket of §1343."
            em.set_author(name=user.display_name)

            em.add_field(name="Currency", value="§{}".format(currency))
            em.add_field(name="Next tax amount", value="§{}".format(get_next_decay(currency)))

            stocks = await ctx.bot.database.get_user_stocks(ctx.author)
            em.add_field(name="Shares held", value=sum(userstock.amount for userstock in stocks))
            em.add_field(name="Asset values", value="§{:.2f}".format(sum(userstock.amount * userstock.stock.price for
                                                                         userstock in stocks)))

            em.set_thumbnail(url=user.avatar_url)
            em.timestamp = ts
            em.set_footer(text="Thanks capitalism!")
            em.colour = user.colour
            await ctx.send(embed=em)
        else:
            await ctx.channel.send("User **{}** has `§{}`.".format(user, currency))

    @currency.command(pass_context=True, aliases=["bottom"])
    async def poorest(self, ctx: Context):
        """
        Shows the top 10 poorest users in this server.
        """
        users = await ctx.bot.database.get_multiple_users(*ctx.message.guild.members, order_by=User.money.asc())

        base = "**Bottom 10 users (in this server):**\n\n```{}```"

        # Create a table using tabulate.
        headers = ["POS", "User", "Currency"]
        table = []

        for n, u in enumerate(users[:10]):
            try:
                member = ctx.message.guild.get_member(u.id).name
                # Unicode and tables suck
                member = member.encode("ascii", errors="replace").decode()
            except AttributeError:
                # Prevent race condition - member leaving between command invocation and here
                continue
            table.append([len(users) - (n + 1), member, u.money])

        # Format the table.
        table = tabulate.tabulate(table, headers=headers, tablefmt="orgtbl")

        fmtted = base.format(table)

        await ctx.channel.send(fmtted)

    @currency.command(pass_context=True, aliases=["top", "leaderboard"])
    async def richest(self, ctx: Context):
        """
        Shows the top 10 richest users in this server.
        """
        users = await ctx.bot.database.get_multiple_users(*ctx.message.guild.members, order_by=User.money.desc())

        base = "**Top 10 users (in this server):**\n\n```{}```"

        # Create a table using tabulate.
        headers = ["POS", "User", "Currency"]
        table = []

        for n, u in enumerate(users[:10]):
            try:
                member = ctx.message.guild.get_member(u.id).name
                # Unicode and tables suck
                member = member.encode("ascii", errors="replace").decode()
            except AttributeError:
                # Prevent race condition - member leaving between command invocation and here
                continue
            table.append([n + 1, member, u.money])

        # Format the table.
        table = tabulate.tabulate(table, headers=headers, tablefmt="orgtbl")

        fmtted = base.format(table)

        await ctx.channel.send(fmtted)


setup = Currency.setup
