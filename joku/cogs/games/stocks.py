"""
Fake stock market system.
"""
import discord
import numpy as np
import tabulate
from asyncio_extras import threadpool
from discord import ChannelType

from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import has_permissions


class Stocks(Cog):
    """
    A fake stocks system.
    """

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
            name += sp[-1][1:5-len(name)]

        return name.upper()

    @commands.group()
    async def stocks(self, ctx: Context):
        """
        Controls the stock market for this server.
        """
        stocks = await ctx.bot.database.get_stocks_for(ctx.guild)

        # OH BOY IT'S TABLE O CLOCK
        headers = ["Name", "Total shares", "Available shares", "Price/share"]
        rows = []

        async with ctx.channel.typing():
            for stock in stocks:
                channel = ctx.guild.get_channel(stock.channel_id)
                if not channel:
                    continue

                name = self._get_name(channel)
                total_available = await ctx.bot.database.get_remaining_stocks(channel)
                rows.append([name, stock.amount, total_available, stock.price])

        table = tabulate.tabulate(rows, headers=headers, tablefmt="orgtbl")
        await ctx.send("```{}```".format(table))

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

setup = Stocks.setup
