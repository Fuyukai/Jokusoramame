"""
Misc cog.
"""
import asyncio
import time

import discord
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import has_permissions


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

    @commands.command()
    @has_permissions(manage_messages=True)
    async def redirect(self, ctx: Context, channel: discord.TextChannel, message: int):
        """
        Redirects a message to another channel.

        The message argument passed must be a message ID.
        To get a message ID you should right click on the on a message and then click "Copy ID". You must have Developer
        Mode enabled to get that functionality.
        """
        o_chan = ctx.channel  # type: discord.TextChannel
        try:
            msg = await o_chan.get_message(message)
        except discord.HTTPException:
            await ctx.send(":x: Could not find that message.")
            return

        # delete it and copy it to the target channel
        em = discord.Embed(title="Redirected by {}".format(ctx.author.name))
        em.description = msg.content
        em.set_author(name=msg.author.name, icon_url=msg.author.avatar_url)
        em.timestamp = msg.created_at
        await msg.delete()
        await ctx.message.delete()
        await channel.send("{}: This message was redirected here from {}:"
                           .format(msg.author.mention, ctx.channel.mention),
                           embed=em)
        # send a link to the channel
        m = await ctx.channel.send(channel.mention)
        await asyncio.sleep(60)
        await m.delete()


setup = Misc.setup
