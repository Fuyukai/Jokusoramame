"""
Fake stock market system.
"""
import datetime
import asyncio
from io import BytesIO

import pytz
import typing
from math import log

import discord
import arrow
import numpy as np
import tabulate
from asyncio_extras import threadpool
from discord.ext import commands
import matplotlib as mpl
from sqlalchemy.orm import Session

from joku.db.tables import Stock

mpl.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.cm as cm

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import has_permissions


class Stocks(Cog):
    """
    A fake stocks system.
    """
    _running = False
    _plot_lock = asyncio.Lock()

    @staticmethod
    def get_hist_mult(x: int) -> float:
        return x / (10 ** np.ceil(log(x, 10)))

    def _get_name(self, channel: discord.TextChannel):
        """
        Gets the stock name for this channel.
        """
        if "-" in channel.name:
            sp = channel.name.split("-")
        elif "_" in channel.name:
            sp = channel.name.split("_")
        else:
            # fuck ur delim
            sp = [channel.name]

        name = ""
        for part in sp:
            if len(name) == 4:
                break

            if not part:
                # bad channels
                continue

            name += part[0]
        else:
            name += sp[-1][1:5 - len(name)]

        return name.upper()

    def _identify_stock(self, channels: typing.Sequence[discord.TextChannel], name: str) -> discord.TextChannel:
        """
        Identifies a stock.
        """
        for channel in channels:
            if self._get_name(channel) == name:
                return channel

    async def ready(self):
        """
        Begins fluctuating stock prices.
        """
        if self._running:
            return

        self._running = True

        try:
            while True:
                # collect all the guilds that have stocks enabled
                guilds = await self.bot.database.get_multiple_guilds(*self.bot.guilds)
                collected = [g for g in guilds if g.stocks_enabled]

                # sleep until the minute
                t = datetime.datetime.utcnow()
                sleeptime = 60 - (t.second + t.microsecond / 1000000.0)
                self.logger.info("Sleeping for {} seconds before changing stocks".format(sleeptime))
                await asyncio.sleep(sleeptime)

                # void warranty

                mappings = []
                for guild in collected:
                    guild = self.bot.connection._guilds.get(guild.id)  # type: discord.Guild
                    if not guild:
                        continue

                    stocks = await self.bot.database.get_stocks_for(guild)

                    for stock in stocks:
                        channel = guild.get_channel(stock.channel_id)
                        if channel is None:
                            continue
                        # update the price
                        history = await self.bot.redis.get_and_pop_history_count(channel)
                        if history != 0:
                            mult = self.get_hist_mult(history)
                        else:
                            mult = 0

                        mult += np.random.lognormal(mean=-2)
                        mult = self.rng.choice([-1, 1]) * mult
                        mult = max(-0.9, min(mult, 0.9))  # clamp multiplier to 0.9 either way
                        mult = 1 + mult

                        old_price = stock.price
                        # clamp prices to [2, 70]
                        new_price = min(70.0, max(2.00, round(old_price * mult, 2)))

                        # edit the stock price
                        mappings.append({
                            "channel_id": stock.channel_id,
                            "price": new_price
                        })
                        self.logger.info("Stock {} gone from {} -> {}".format(channel.id, old_price, new_price))

                async with threadpool():
                    with self.bot.database.get_session() as sess:
                        assert isinstance(sess, Session)
                        sess.bulk_update_mappings(Stock, mappings)

        finally:
            self._running = False

    async def on_message(self, message: discord.Message):
        # increment history for this channel
        if message.channel.guild is None:
            return

        await self.bot.redis.increase_history_count(message.channel)

    @commands.group(invoke_without_command=True, aliases=["stock"])
    async def stocks(self, ctx: Context):
        """
        Controls the stock market for this server.
        """
        stocks = await ctx.bot.database.get_stocks_for(ctx.guild)

        # OH BOY IT'S TABLE O CLOCK
        headers = ["Name", "Total shares", "Available shares", "Price/share", "%age remaining"]
        rows = []

        async with ctx.channel.typing():
            for stock in stocks:
                channel = ctx.guild.get_channel(stock.channel_id)
                if not channel:
                    continue

                name = self._get_name(channel)
                total_available = await ctx.bot.database.get_remaining_stocks(channel)
                rows.append([name, stock.amount, total_available,
                             "{:.2f}".format(stock.price), round(((total_available / stock.amount) * 100), 2)])

        table = tabulate.tabulate(rows, headers=headers, tablefmt="orgtbl", disable_numparse=True)
        await ctx.send("```{}```".format(table))

    @stocks.command()
    async def portfolio(self, ctx: Context):
        """
        Shows off your current stock portfolio for this guild.
        """
        stocks = await ctx.bot.database.get_user_stocks(ctx.author, guild=ctx.guild)

        headers = ["Name", "Shares", "Total value", "%age of stock"]
        rows = []

        for userstock in stocks:
            channel = ctx.guild.get_channel(userstock.stock.channel_id)
            if not channel:
                continue

            if userstock.amount <= 0:
                continue

            rows.append([self._get_name(channel), userstock.amount,
                         "{:.2f}".format(float(userstock.amount * userstock.stock.price)),
                         "{:.2f}".format((userstock.amount / userstock.stock.amount) * 100)])

        table = tabulate.tabulate(rows, headers=headers, tablefmt="orgtbl", disable_numparse=True)
        await ctx.send("```{}```".format(table))

    @stocks.command()
    async def view(self, ctx: Context, stock: str):
        """
        View the current status of a stock.
        """
        channel = self._identify_stock(ctx.guild.channels, stock.upper())
        if channel is None:
            await ctx.send(":x: That stock does not exist.")
            return

        stock = await ctx.bot.database.get_stock(channel)
        remaining = await ctx.bot.database.get_remaining_stocks(channel)

        last_hour = await ctx.bot.redis.get_historical_prices(channel)
        last_hour_arr = np.array(last_hour)

        em = discord.Embed(title="Viewing stock for **{}**".format(self._get_name(channel)))
        em.description = "Average is taken over the last **hour**.\n" \
                         "Minute running diff is difference from **last minute**.\n" \
                         "Hourly running diff is difference from **the beginning of the hour**."

        em.add_field(name="Price", value="**§{:.2f}**".format(stock.price))
        em.add_field(name="Total amount", value="**{}**".format(stock.amount))

        av_perc = round(((remaining / stock.amount) * 100), 2)

        em.add_field(name="Available amount", value="**{}** *({}%)*".format(remaining, av_perc))

        # calculate running averages
        mean = np.mean(last_hour_arr)
        mean = round(mean, 2)  # only use rounded mean

        # used for colour calculations
        hits = []

        # pretty ugly
        def _get_relative(val) -> typing.Tuple[str, float]:
            nonlocal hits
            relative = stock.price - val
            if relative < 0:
                sym = "⬇"
                hits.append(False)
                relative = np.abs(relative)
            else:
                hits.append(True)
                sym = "⬆"

            return sym, relative

        em.add_field(name="Fluctuation from avg", value="{} §{:.2f}".format(*_get_relative(mean)))

        # calculate difference from last 1m
        em.add_field(name="Minute running diff", value="{} §{:.2f}".format(*_get_relative(last_hour[-2])))

        # calculate difference from start of hour
        em.add_field(name="Hourly running diff", value="{} §{:.2f}".format(*_get_relative(last_hour[0])))

        # calculate colour
        s = sum(hits)
        if s == 0:
            em.colour = discord.Colour.red()
        elif s == 1:
            em.colour = discord.Colour.dark_orange()
        elif s == 2:
            em.colour = discord.Colour.gold()
        else:
            em.colour = discord.Colour.green()

        em.set_footer(text="1st Stock Market of Joku")
        em.timestamp = datetime.datetime.now()
        await ctx.send(embed=em)

    @stocks.command()
    async def buy(self, ctx: Context, stock: str, amount: int):
        """
        Buys a stock.
        """
        # try and identify the stock
        channel = self._identify_stock(ctx.guild.channels, stock.upper())
        if channel is None:
            await ctx.send(":x: That stock does not exist.")
            return

        total_available = await ctx.bot.database.get_remaining_stocks(channel)
        if total_available < 1:
            await ctx.send(":x: This stock is all sold out.")
            return

        if total_available - amount < 0:
            await ctx.send(":x: Cannot buy more shares than are in existence.")
            return

        if total_available * 0.4 < amount:
            await ctx.send(":x: You cannot own more than 40% of a given stock.")
            return

        stock = await ctx.bot.database.get_stock(channel)
        price = stock.price * amount

        user = await ctx.bot.database.get_or_create_user(ctx.author)
        if user.money < price:
            await ctx.send(":x: You need `§{:.2f}` to buy this.".format(price))
            return

        await ctx.bot.database.change_user_stock_amount(ctx.author, channel, amount=amount)
        await ctx.send(":heavy_check_mark: Brought {} stocks for `§{:.2f}`.".format(amount, price))

    @stocks.command()
    async def sell(self, ctx: Context, stock: str, amount: int):
        """
        Sells a stock.
        """
        if amount <= 0:
            await ctx.send(":x: Nice try.")
            return

        # try and identify the stock
        channel = self._identify_stock(ctx.guild.channels, stock.upper())
        if channel is None:
            await ctx.send(":x: That stock does not exist.")
            return

        us = await ctx.bot.database.get_user_stock(ctx.author, channel)
        if us is None or us.amount == 0:  # never delete userstock, is inefficient
            await ctx.send(":x: You do not own any of this stock.")
            return

        if us.amount < amount:
            await ctx.send(":x: Cannot sell more shares than you have.")
            return

        await ctx.bot.database.change_user_stock_amount(ctx.author, channel, amount=-amount)
        await ctx.send(":heavy_check_mark: Sold {} stocks for `§{:.2f}`.".format(amount, us.stock.price * amount))

    @stocks.command(aliases=["plot"])
    async def graph(self, ctx: Context):
        """
        Graphs the stock trends for this channel.
        """
        stocks = await ctx.bot.database.get_stocks_for(ctx.guild)

        tds = []
        for c in stocks:
            channel = ctx.guild.get_channel(c.channel_id)
            if not channel:
                continue

            name = self._get_name(channel)
            tds.append((name, await ctx.bot.redis.get_historical_prices(channel)))

        async with ctx.channel.typing():
            async with self._plot_lock:
                async with threadpool():
                    # calculate the dates
                    dates = [arrow.now(pytz.UTC).replace(minutes=-i) for i in range(0, len(tds[0][1]))]
                    dates = list(reversed([dt.strftime("%H:%M") for dt in dates]))

                    # axis labels
                    plt.xlabel("Time UTC (HH:MM)")
                    plt.ylabel("Price (§)")

                    # hacky to get the right bottom
                    x = np.arange(0, len(tds[0][1]))

                    # current line colour legend
                    legend = []

                    # rainbowify the lines
                    colours = cm.rainbow(np.linspace(0, 1, len(tds)))
                    for history, colour in zip(tds, colours):
                        # extract the name and add it to the legend
                        name, values = history
                        legend.append(name)
                        # plot against dates
                        plt.plot(x, values, color=colour)

                    # xticks the data
                    plt.xticks(x, dates, rotation=270)

                    plt.title("1st Stock Market of Joku")

                    # only show every 2nd tick
                    ax = plt.gca()
                    plt.setp(ax.get_xticklabels()[::2], visible=False)

                    plt.legend(legend, loc="best")
                    plt.tight_layout()

                    buf = BytesIO()
                    plt.savefig(buf, format="png")

                    # Don't send 0-byte files
                    buf.seek(0)

                    # Cleanup.
                    plt.clf()
                    plt.cla()

        await ctx.channel.send(file=buf, filename="plot.png")

    @stocks.command(name="setup")
    @has_permissions(manage_server=True)
    async def _setup(self, ctx: Context):
        """
        Enables stocks for this server.
        """
        guild = await ctx.bot.database.get_or_create_guild(ctx.guild)
        if guild.stocks_enabled:
            await ctx.send(":x: Stocks are already enabled for this guild.")
            return

        await ctx.send(":hourglass: Generating stock amounts and initial prices for this server...")

        count = 0
        total_value = 0
        for channel in ctx.guild.channels:
            if not isinstance(channel, discord.TextChannel):
                continue

            if channel.overwrites_for(ctx.guild.default_role).read_messages is False:
                continue

            count += 1
            shares_available = min(1400, 700 + ((channel.id & 0xFFFFFFFF) >> 22))
            base_price = round(np.random.uniform(17, 43), 2)
            total_value += (shares_available * base_price)
            self.logger.info("Adding {} stocks at {} each for {}.".format(shares_available, base_price, channel.name))
            await ctx.bot.database.change_stock(channel, amount=shares_available, price=base_price)

        async with threadpool():
            with ctx.bot.database.get_session() as sess:
                guild.stocks_enabled = True
                sess.merge(guild)

        await ctx.send(":heavy_check_mark: Injected `§{}` into the market over `{}` stocks.".format(round(
            total_value, 2), count))

        await ctx.send(":warning: If you have had a lot of messages between adding the bot and setting up the stocks "
                       "system, stocks may see huge initial swings as history is counted.")


setup = Stocks.setup
