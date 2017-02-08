"""
Reminders cog. Database backed to ensure persistence between bot restarts.
"""
import asyncio
import logging
import time

import discord

from joku.cogs._common import Cog
from joku.db.tables import Reminder


logger = logging.getLogger("Jokusoramame.Reminders")


class Reminders(Cog):
    _is_running_reminders = False

    _currently_running = {}

    async def _fire_reminder(self, reminder: Reminder):
        """
        Fires a reminder object to be ran.
        """
        # Wrap everything in a try/finally.
        try:

            if reminder.enabled is False:
                # race conditions?
                return

            # check to see if the reminder is valid or not
            channel = self.bot.get_channel(reminder.channel_id)
            if channel is None:
                # cancel it
                await self.bot.database.cancel_reminder(reminder.id)
                return

            guild = channel.guild  # type: discord.Guild
            member = guild.get_member(reminder.user_id)
            if not member:
                await self.bot.database.cancel_reminder(reminder.user_id)
                return

            self._currently_running[reminder.id] = True

            time_left = reminder.reminding_at.timestamp() - time.time()
            # sleep for that many seconds before waking up and sending the messages.
            await asyncio.sleep(time_left)

            # send the reminder
            try:
                channel.send(":alarm: {}, you wanted to be reminded of: `{}`".format(member.mention, reminder.text))
            except discord.HTTPException:
                logger.warning("Failed to send reminder `{}`!".format(reminder.id))
            finally:
                # todo: repeating reminders
                reminder.enabled = False

            # mark it as disabled
            if reminder.enabled is False:
                await self.bot.database.cancel_reminder(reminder.id)

        finally:
            self._currently_running.pop(reminder.id, None)

    async def ready(self):
        # Start a reminder polling task.
        if self._is_running_reminders is True:
            return

        self._is_running_reminders = True

        try:
            while True:
                # Scan the reminders firing in the next 300 seconds.
                reminders = await self.bot.database.scan_reminders(within=300)
                for reminder in reminders:
                    self.bot.loop.create_task(self._fire_reminder(reminder))

                # Sleep for 300 seconds afterwards.
                await asyncio.sleep(300)
        finally:
            # Stop running reminders so that a reload will cause them to start again.
            self._is_running_reminders = False
