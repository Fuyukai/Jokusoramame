"""
Do not disturb cop.
"""
import discord
from discord.ext import commands

from joku.cogs._common import Cog


class InvisCop(Cog):
    async def on_message(self, message: discord.Message):
        """
        Checks for people on invisible, and deletes their message.
        """
        if message.server is None:
            return

        if message.author.bot:
            return

        enabled = (await self.bot.rethinkdb.get_setting(message.server, "dndcop", {})).get("status") == 1

        if enabled:
            # Check the author's status for being not ONLINE or AWAY.
            assert isinstance(message.author, discord.Member)
            if message.author.status is discord.Status.offline:
                # Check if they have Manage Messages for this channel.
                # If they do, don't delete their message.
                if message.author.permissions_in(message.channel).manage_messages:
                    return

                # Delete their message.
                try:
                    await self.bot.delete_message(message)
                except discord.Forbidden:
                    # oh well
                    return

setup = InvisCop.setup
