"""
Misc cog.
"""
import asyncio
from itertools import islice

import discord
import google
import time

from asyncio_extras import threadpool
from discord.ext import commands

from joku.bot import Context
from joku.cogs._common import Cog


class Misc(Cog):
    @commands.command()
    async def ping(self, ctx: Context):
        """
        Pong.
        """
        before = time.monotonic()
        msg = await ctx.send(":ping_pong: Ping!")  # type: discord.Message
        after = time.monotonic()
        await msg.edit(content=":ping_pong: Ping! | {}ms".format(round((after - before) * 1000, 2)))

    @commands.command()
    async def cleanup(self, ctx: Context):
        """
        Cleans up bot messages in the last 100 messages.
        """
        channel = ctx.channel  # type: discord.TextChannel
        if channel.permissions_for(ctx.guild.me).manage_messages:
            count = len(await channel.purge(limit=100, check=lambda m: m.author == ctx.guild.me, before=ctx.message))
        else:
            count = 0
            async for message in channel.history(limit=100, before=ctx.message):
                if message.author == ctx.guild.me:
                    await message.delete()
                    count += 1

        m = await ctx.send(":heavy_check_mark: Cleaned up `{}` messages.".format(count))
        await asyncio.sleep(5)
        await m.delete()


setup = Misc.setup
