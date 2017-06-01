"""
Do not disturb cop.
"""
import discord
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import has_permissions, mod_command


class InvisCop(Cog):
    @commands.command(pass_context=True)
    @has_permissions(manage_guild=True, manage_messages=True)
    @mod_command()
    async def inviscop(self, ctx: Context, *, status: str = None):
        """
        Manages the Invisible cop

        The Invisible Cop automatically deletes any messages of users with Invisible on.
        """
        if status is None:
            # Check the status.
            setting = await ctx.bot.database.get_setting(ctx.message.guild, "dndcop")
            if setting == "true":
                await ctx.channel.send("Invis Cop is currently **on.**")
            else:
                await ctx.channel.send("Invis Cop is currently **off.**")
        else:
            if status.lower() == "on":
                await ctx.bot.database.set_setting(ctx.message.guild, "dndcop", "true")
                await ctx.channel.send(":heavy_check_mark: Turned Invis Cop on.")
                return
            elif status.lower() == "off":
                await ctx.bot.database.set_setting(ctx.message.guild, "dndcop", "false")
                await ctx.channel.send(":heavy_check_mark: Turned Invis Cop off.")
                return
            else:
                await ctx.channel.send(":x: No.")

    async def on_message(self, message: discord.Message):
        """
        Checks for people on invisible, and deletes their message.
        """
        if message.guild is None:
            return

        if message.author.bot:
            return

        enabled = await self.bot.database.get_setting(message.guild, "dndcop", {})

        if enabled == "true":
            # Check the author's status for being not ONLINE or AWAY.
            assert isinstance(message.author, discord.Member)
            if message.author.status is discord.Status.offline:
                # Check if they have Manage Messages for this channel.
                # If they do, don't delete their message.
                if message.author.permissions_in(message.channel).manage_messages \
                        and message.guild.id != 196103719975124992:
                    return

                # Delete their message.
                try:
                    await message.delete()
                except discord.Forbidden:
                    # oh well
                    return

setup = InvisCop.setup
