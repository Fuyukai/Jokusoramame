"""
Cog that handles event listeners and such.
"""
import discord

import rethinkdb as r

from joku.bot import Jokusoramame


class Events(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

    async def on_member_join(self, member: discord.Member):
        """
        Called when a member joins.

        Checks if this server is subscribed to joins, and formats the welcome message as appropriate.
        """
        enabled = await self.bot.rethinkdb.get_setting(member.server, "events")
        if not enabled:
            return

        events = enabled.get("events", {})
        chan_id = events.get("joins")
        if chan_id:
            # Get the channel, and send the welcome message to it.
            channel = member.server.get_channel(chan_id)
            if not channel:
                # Not good!
                return

            message = await r.table("settings")\
                .get_all(member.server.id, index="server_id")\
                .filter({"setting_name": "event_msg", "event": "joins"}).run(self.bot.rethinkdb.connection)

            i =     