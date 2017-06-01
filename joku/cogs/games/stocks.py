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
from sqlalchemy import func
from sqlalchemy.orm import Session

from joku.db.tables import Stock, UserStock

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

    def _identify_stock(self, channels: typing.Sequence[discord.abc.GuildChannel], name: str) -> discord.TextChannel:
        """
        Identifies a stock.
        """
        for channel in channels:
            if not isinstance(channel, discord.TextChannel):
                continue
            if self._get_name(channel) == name:
                return channel

    async def flucutate_stock(self, stock: Stock, remaining: int):
        """
        Fluctuates a stock.
        
        Returns a 3 item tuple -> price, amount, crashed: bool
        If crashed is True then price and amount are ignored
        """
        channel = self.bot.get_channel(stock.channel_id)

        # 1 crash per 6 hours
        if self.rng.randint(0, 2880) == 3:
            return 2.0, stock.amount, False

        # TODO: History multiplier, but properly this time?

        # Initial multiplier is a random amount between 0.1 and 0.5.
        # No lognormal here, F
        mult = 0.5 * np.random.rand()
        # Make it either positive or negative to make the price either decrease or increase.
        mult = self.rng.choice([-1, 1]) * mult
        # Add 1 to the mult to make sure it's always positive.
        mult += 1
        # Calculate the new final price for the stock.
        new_price = round(max(2.0, stock.price * mult), 2)

        # Amount calculation.
        # Get the total amount remaining.
        if remaining <= 0:
            # Freeze the stock.
            return new_price, stock.amount, False

        # Calculate how much to go up or down.
        dilute = int(np.random.laplace(scale=3))
        if dilute < 0:
            # Prevent it from going below the remaining shares.
            dilute = max(-remaining, dilute)

        # Add the amount on.
        new_amount = min(13000, max(900, stock.amount + dilute))

        return new_price, new_amount, False

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

                stock_mappings = []
                us_mappings = []
                coros = []
                for guild in collected:
                    try:
                        guild = self.bot.connection._get_guild(guild.id)  # type: discord.Guild
                    except:
                        guild = self.bot._connection._get_guild(guild.id)
                    if not guild:
                        continue

                    stocks = await self.bot.database.get_stocks_for(guild)
                    remaining = await self.bot.database.bulk_get_remaining_stocks(*stocks)
                    for stock in stocks:
                        # update the price
                        channel = guild.get_channel(stock.channel_id)
                        if channel is None:
                            continue

                        final_price, \
                        new_amount, \
                        crashed = await self.flucutate_stock(stock, remaining.get(stock.channel_id, stock.amount))

                        if crashed:
                            # should work :fingers_crossed:
                            for us in stock.users:
                                us_mappings.append({
                                    "id": us.id,
                                    "crashed": True,
                                    "crashed_at": stock.price
                                })

                        # edit the stock price
                        stock_mappings.append({
                            "channel_id": stock.channel_id,
                            "price": final_price,
                            "amount": new_amount
                        })
                        await self.bot.redis.update_stock_prices(channel, final_price)

                        self.logger.info("Stock {} gone from value {} -> {}, "
                                         "amount {} -> {}, crashed: {}".format(stock.channel_id, stock.price,
                                                                               final_price,
                                                                               stock.amount, new_amount, crashed))

                async with threadpool():
                    with self.bot.database.get_session() as sess:
                        assert isinstance(sess, Session)
                        sess.bulk_update_mappings(Stock, stock_mappings)
                        sess.bulk_update_mappings(UserStock, us_mappings)

        finally:
            self._running = False

    async def on_message(self, message: discord.Message):
        # increment history for this channel
        if message.channel.guild is None:
            return

        await self.bot.redis.increase_history_count(message.channel)

    @commands.group(pass_context=True, invoke_without_command=True, aliases=["shares", "share", "asset"])
    async def assets(self, ctx: Context, *, target: discord.Member = None):
        """
        Gets the current amount of § a user has in assets.

        If no target is provided, it will show your worth in assets
        """
        user = target or ctx.message.author
        if user.bot:
            await ctx.channel.send(":x: Bots cannot own shares.")
            return

        guild = await ctx.bot.database.get_or_create_guild(ctx.guild)
        if not guild.stocks_enabled:
            await ctx.send(":x: Stocks are not enabled for this server.")
            return

        # Display only Assets the user owns (stolen from currency)
        if ctx.channel.permissions_for(ctx.guild.me).embed_links:
            day = self.rng.randint(1, 31)
            hour, minute, second = self.rng.randint(0, 23), self.rng.randint(0, 59), self.rng.randint(0, 59)

            ts = datetime.datetime(year=2008, month=7, day=day, hour=hour, minute=minute, second=second)

            em = discord.Embed(title="1st Stock Market of Joku")
            em.description = "Your asset value is based on best estimates from current market prices."
            em.set_author(name=user.display_name)

            stocks = await ctx.bot.database.get_user_stocks(user)
            em.add_field(name="Shares held", value=sum(userstock.amount for userstock in stocks))
            em.add_field(name="Asset values", value="§{:.2f}".format(sum(userstock.amount * userstock.stock.price
                                                                         for userstock in stocks)))

            em.set_thumbnail(url=user.avatar_url)
            em.timestamp = ts
            em.set_footer(text="Thanks capitalism!")
            em.colour = user.colour
            await ctx.send(embed=em)
        else:
            stocks = await ctx.bot.database.get_user_stocks(user)
            await ctx.channel.send(
                "User **{}** has `§{}` assets worth `§{}`.".format(user,
                                                                   sum(userstock.amount for userstock in stocks),
                                                                   sum(userstock.amount * userstock.stock.price for
                                                                       userstock in stocks)))

    @assets.command(pass_context=True, aliases=["top", "leaderboard"])
    async def richest(self, ctx: Context, *, what: str = "value"):
        """
        Shows the top 10 stock holders in this guild by value of assets.
        Adding amount or owned will rank by assets owned.
        """
        guild = await ctx.bot.database.get_or_create_guild(ctx.guild)
        if not guild.stocks_enabled:
            await ctx.send(":x: Stocks are not enabled for this server.")
            return

        users = await ctx.bot.database.get_multiple_users(*ctx.message.guild.members)

        # Append a column to users holding asset total and asset worth
        f_users = []
        for user in users:
            stocks = await ctx.bot.database.get_user_stocks(user)
            f_users.append([user, sum(userstock.amount for userstock in stocks),
                            sum(userstock.amount * userstock.stock.price for userstock in stocks)])

        if (what == "amount") or (what == "owned"):  # order by stock amount
            f_users = list(sorted(f_users, key=lambda user: user[1], reverse=True))
        else:  # what == default: order by asset worth
            f_users = list(sorted(f_users, key=lambda user: user[2], reverse=True))
        base = "**Top 10 users (in this server):**\n\n```{}```"

        # Create a table using tabulate.
        if (what == "amount") or (what == "owned"):
            headers = ["POS", "User", "Assets Owned"]
        else:  # what = default: order by value of stock worth
            headers = ["POS", "User", "Total Value"]
        table = []

        for n, u in enumerate(f_users[:10]):
            try:
                member = ctx.message.guild.get_member(u[0].id).name
                # Unicode and tables suck
                member = member.encode("ascii", errors="replace").decode()
            except AttributeError:
                # Prevent race condition - member leaving between command invocation and here
                continue
            if (what == "owned") or (what == "amount"):
                table.append([n + 1, member, u[1]])
            else:
                table.append([n + 1, member, "§{:.2f}".format(u[2])])

        # Format the table.
        table = tabulate.tabulate(table, headers=headers, tablefmt="orgtbl")

        fmtted = base.format(table)

        await ctx.channel.send(fmtted)

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

    @stocks.command(hidden=True)
    async def taxes(self, ctx: Context):
        em = discord.Embed()
        em.description = "<:ancap:282526484004995072>"
        await ctx.send(embed=em)

    @stocks.command()
    async def info(self, ctx: Context):
        """
        Shows the current stock info for this guild.
        """
        guild = await ctx.bot.database.get_or_create_guild(ctx.guild)
        if not guild.stocks_enabled:
            await ctx.send(":x: Stocks are not enabled for this server.")
            return

        em = discord.Embed(title="1st Stock Market of Joku")
        em.description = "Displaying info about stocks for {.name}:\n\n" \
                         "The **individual share cap** is the maximum number of shares one person can own.\n" \
                         "The **market owned percentage** is what percentage is owned by users.".format(ctx.guild)

        # calc market value
        stocks = await ctx.bot.database.get_stocks_for(ctx.guild)
        total = sum(stock.amount for stock in stocks)
        val = sum(stock.amount * stock.price for stock in stocks)

        em.add_field(name="Stocks available", value=len(stocks))
        em.add_field(name="Market value", value="§{:.2f}".format(val))
        em.add_field(name="Individual share cap", value=total // 10)

        async with threadpool():
            with self.bot.database.get_session() as sess:
                r = sess.query(func.sum(UserStock.amount)).join(Stock).filter(Stock.guild_id == ctx.guild.id).scalar()

        em.add_field(name="Total shares", value=int(total))

        perc = (r / total) * 100

        em.add_field(name="Market owned percentage", value="{:.2f}%".format(perc))
        em.add_field(name="Remaining shares", value=(total - r))
        em.colour = ctx.author.colour
        em.timestamp = datetime.datetime.now()
        await ctx.send(embed=em)

    @stocks.command()
    async def portfolio(self, ctx: Context, target: discord.Member = None):
        """
        Shows off your current stock portfolio for this guild.
        """
        target = target or ctx.author
        stocks = await ctx.bot.database.get_user_stocks(target, guild=ctx.guild)

        headers = ["Name", "Shares", "Share price", "Total value", "%age of stock"]
        rows = []

        for userstock in stocks:
            channel = ctx.guild.get_channel(userstock.stock.channel_id)
            if not channel:
                continue

            if userstock.amount <= 0:
                continue

            if userstock.crashed:
                share_price = "0.0 (Crashed)"
                total = "0.0 (Crashed)"
            else:
                share_price = userstock.stock.price
                total = "{:.2f}".format(float(userstock.amount * userstock.stock.price))

            rows.append([self._get_name(channel), userstock.amount,
                         share_price, total,
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

        amnt = sum(us.amount for us in (await ctx.bot.database.get_user_stocks(ctx.author, guild=ctx.guild)) if us)
        total = sum(stock.amount for stock in (await ctx.bot.database.get_stocks_for(ctx.guild)))
        if amnt > total // 10:
            await ctx.channel.send(":x: Monopolies do nothing but hurt the environment "
                                   "(you need less than `{}` total shares to buy any more).".format(total // 10))
            return

        total_available = await ctx.bot.database.get_remaining_stocks(channel)
        if total_available < 1:
            await ctx.send(":x: This stock is all sold out.")
            return

        if total_available - amount < 0:
            await ctx.send(":x: Cannot buy more shares than are in existence.")
            return

        stock = await ctx.bot.database.get_stock(channel)
        us = await ctx.bot.database.get_user_stock(ctx.author, channel)

        if us and us.crashed is True and us.amount >= 1:
            await ctx.send(":x: This stock crashed. You must sell your remaining shares.")
            return

        try:
            us_amount = us.amount or 0
        except AttributeError:  # us is None
            us_amount = 0

        if stock.amount * 0.4 < us_amount + amount:
            await ctx.send(":x: You cannot own more than 40% (`{}` shares ) of this stock."
                           .format(int(stock.amount * 0.4)))
            return

        price = stock.price * amount

        user = await ctx.bot.database.get_or_create_user(ctx.author)
        if user.money < price:
            await ctx.send(":x: You need `§{:.2f}` to buy this.".format(price))
            return

        await ctx.bot.database.change_user_stock_amount(ctx.author, channel, amount=amount, crashed=False)
        await ctx.send(":heavy_check_mark: Brought {} stocks for `§{:.2f}`. ".format(amount, price))

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

        if us.crashed:
            absorbed = us.crashed_at * us.amount
            absorbed = absorbed / 4

            await ctx.send(":chart_with_downwards_trend: This stock crashed and you've been forced to absorb some "
                           "of the cost."
                           "You have lost `§{:.2f}`, and all your shares in this stock.".format(absorbed))
            await ctx.bot.database.change_user_stock_amount(ctx.author, channel, amount=-us.amount, update_price=False,
                                                            crashed=False)
            await ctx.bot.database.update_user_currency(ctx.author, currency_to_add=-absorbed)

            return

        if us.amount < amount:
            await ctx.send(":x: Cannot sell more shares than you have.")
            return

        # calculate commission
        if us.amount + amount <= us.stock.amount * 0.1:
            tax = 0
        elif us.amount + amount <= us.stock.amount * 0.25:
            # 10%-25% of the stock is taxed at 30%
            tax = amount * (us.stock.price * 0.3)
        else:
            # 25%-40% of the stock is taxed at 45%
            tax = amount * (us.stock.price * 0.45)

        tax = int(tax)

        await ctx.bot.database.change_user_stock_amount(ctx.author, channel, amount=-amount)
        await ctx.bot.database.update_user_currency(ctx.author, -tax)
        await ctx.send(":heavy_check_mark: Sold {} stocks for `§{:.2f}`. "
                       "Additionally, you paid `§{}` tax on this.".format(amount, us.stock.price * amount, tax))

    @stocks.command(aliases=["plot"])
    async def graph(self, ctx: Context, *, what: str = "all"):
        """
        Graphs the stock trends for this channel.
        """
        if not ctx.channel.permissions_for(ctx.author).attach_files:
            await ctx.send(":x: I need Attach Files permissions.")
            return

        stocks = await ctx.bot.database.get_stocks_for(ctx.guild)
        user_stocks = await ctx.bot.database.get_user_stocks(ctx.author, guild=ctx.guild)

        tds = []
        for c in stocks:
            channel = ctx.guild.get_channel(c.channel_id)
            if not channel:
                continue

            name = self._get_name(channel)
            tds.append((name, await ctx.bot.redis.get_historical_prices(channel)))

        # collect user stocks
        uds = []
        for u_s in user_stocks:
            # if amount <= 0 dont add it as owned
            if u_s.amount <= 0:
                continue

            channel = ctx.guild.get_channel(u_s.stock.channel_id)
            if not channel:
                continue

            name = self._get_name(channel)
            uds.append(name)

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

                    # if plotting portfolio, only plot the ones the user owns
                    if what == "portfolio":
                        n = []

                        for q in tds:
                            # check if name in user stock names
                            if q[0] in uds:
                                # mark for plotting
                                n.append(q)

                        # overwrite tds
                        tds = n

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
    @has_permissions(manage_guild=True)
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
