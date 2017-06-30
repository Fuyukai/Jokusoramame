"""
Reminders cog. Database backed to ensure persistence between bot restarts.
"""
import asyncio
import datetime
import logging

import discord
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.utils import parse_time
from joku.db.tables import Reminder

logger = logging.getLogger("Jokusoramame.Reminders")


class Reminders(Cog):
    _is_running_reminders = asyncio.Lock()

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
                self.logger.warning("Reminder channel was empty - not reminding...")
                await self.bot.database.cancel_reminder(reminder.id)
                return

            guild = channel.guild  # type: discord.Guild
            member = guild.get_member(reminder.user_id)
            if not member:
                self.logger.warning("Reminder member was dead - not reminding...")
                await self.bot.database.cancel_reminder(reminder.user_id)
                return

            self._currently_running[reminder.id] = True

            # lol local time
            time_left = reminder.reminding_at.timestamp() - datetime.datetime.utcnow().timestamp()
            # sleep for that many seconds before waking up and sending the messages.
            await asyncio.sleep(time_left)

            # send the reminder
            try:
                await channel.send(":alarm_clock: {}, you wanted to be reminded of: `{}`".format(member.mention,
                                                                                                 reminder.text))
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
        if self._is_running_reminders.locked():
            return

        async with self._is_running_reminders:
            while True:
                # Scan the reminders firing in the next 300 seconds.
                reminders = await self.bot.database.scan_reminders(within=300)
                for reminder in reminders:
                    self.bot.loop.create_task(self._fire_reminder(reminder))

                # Sleep for 300 seconds afterwards.
                await asyncio.sleep(300)

    @commands.command()
    async def remind(self, ctx: Context, tstr: str, *, content: str):
        """
        Sets a reminder to be ran in the future.
        """
        _ = parse_time(tstr, seconds=False)
        if _ is None:
            await ctx.send(":x: Invalid time string.")
            return

        dt, seconds = _

        content = content.replace("`", "´").replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")

        reminder = await ctx.bot.database.create_reminder(ctx.channel, ctx.author, content,
                                                          remind_at=dt)
        if seconds < 300:
            # make the reminder immediately.
            t = self.bot.loop.create_task(self._fire_reminder(reminder))
        else:
            t = asyncio.sleep(0)

        em = discord.Embed(title="Remembering things so you don't have to")
        em.description = content
        em.set_footer(text="Reminding at: ")
        em.timestamp = dt

        await ctx.send(embed=em)
        await t


setup = Reminders.setup
