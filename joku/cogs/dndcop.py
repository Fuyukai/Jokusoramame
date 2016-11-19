"""
Do not disturb cop.
"""
import discord
from discord.ext import commands

from joku.cogs._common import Cog


class DNDCop(Cog):
    async def on_message(self, message: discord.Message):
        """
        Checks for people on DND, and deletes their message.
        """
        if message.server is None:
            return

        enabled = ((await self.bot.rethinkdb.get_setting(message.server, "dndcop")) or {}).get("status") == 1

        if enabled:
            # Check the author's status for being not ONLINE or AWAY.
            assert isinstance(message.author, discord.Member)
            if message.author.status not in [discord.Status.online, discord.Status.idle]:
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

setup = DNDCop.setup
