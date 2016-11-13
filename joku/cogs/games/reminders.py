"""
Cog for reminders.

Reminders are database-backed - they persist in the database.
That means between bot crashes, the reminders persist.
"""
import time

import asyncio

import datetime

import tabulate
from discord.ext import commands
from math import ceil

import rethinkdb as r
from parsedatetime import Calendar

from joku.bot import Jokusoramame, Context
from joku.utils import paginate_table


class Reminders(object):
    # Create the empty datetime to be used for the relative datetime.
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

        self._is_running_reminders = False

    async def _run_reminder(self, record: dict):
        channel = self.bot.get_channel(record["channel_id"])
        if not channel:
            # Probably not on this shard.
            return
        server = channel.server
        member = server.get_member(record["user_id"])

        # Wait until we need to remind them.
        reminder_time = record["expiration"] - time.time()
        if reminder_time > 300:
            # Don't bother.
            return

        await asyncio.sleep(reminder_time)

        # Send the message, and remove it from the database.
        fmt = ":alarm_clock: {.mention}, you wanted to be reminded of: `{}`".format(member, record["content"])
        try:
            await self.bot.send_message(channel, fmt)
        except:
            self.bot.logger.error("Failed to send reminder.")
            self.bot.logger.exception()
            # Delete it from the DB.
            record["repeating"] = False

        # Delete from the database.
        r_id = record.get("id")
        if not r_id:
            # Non database-backed reminder.
            return

        # Check for repeating reminders.
        if record.get("repeating", False) is True:
            # Move the next time down by repeat_time.
            record["expiration"] = record["expiration"] + record["repeat_time"]
            i = await r.table("reminders").insert(record, conflict="update").run(self.bot.rethinkdb.connection)
        else:
            # Remove it from the database.
            i = await r.table("reminders").get(r_id).delete().run(self.bot.rethinkdb.connection)
        return i

    async def ready(self):
        # Don't do anything if the DB task already exists.
        if self._is_running_reminders:
            return

        self._is_running_reminders = True

        # Scan the reminders table periodically,
        while True:
            try:
                records = await r.table("reminders").run(self.bot.rethinkdb.connection)

                # Pray!
                async for record in records:
                    # Check the reminder time.
                    # If it's less than 5 minutes, create a reminder coroutine.
                    time_left = record.get("expiration") - time.time()
                    if time_left < 300:
                        self.bot.loop.create_task(self._run_reminder(record))

                        # Otherwise, don't bother with the reminder.

            except Exception:
                self.bot.logger.exception()
            finally:
                await asyncio.sleep(300)

    @commands.group(pass_context=True, invoke_without_command=True, aliases=["reminder"])
    async def remind(self, ctx: Context, duration: str, *, reminder_text: str):
        """
        Sets a reminder to be run in the future.

        Reminders are database-backed, and as such will persist even if the bot crashes.
        The duration can be a time-string that `dateutil.parser` can parse - this means it can be an absolute
        """
        calendar = Calendar()
        t_struct, parse_status = calendar.parse(duration)
        if parse_status == 0:
            await ctx.bot.say(":x: Invalid time format.")
            return

        dt = datetime.datetime(*t_struct[:6])

        timestamp = dt.timestamp()

        object = {
            "user_id": ctx.message.author.id,
            "channel_id": ctx.message.channel.id,
            "expiration": timestamp,
            "content": reminder_text
        }

        # Should we add it to the database, or just make a reminder?
        diff = timestamp - time.time()
        if diff < 300:
            # Just create a reminder now.
            ctx.bot.loop.create_task(self._run_reminder(object))
        else:
            # Add it to the database.
            i = await r.table("reminders").insert(object).run(ctx.bot.rethinkdb.connection)

        await ctx.bot.say(":heavy_check_mark: Will remind you at `{}`.".format(dt))

    @remind.command(pass_context=True, aliases=["repeating"])
    async def repeat(self, ctx: Context, duration: str, *, reminder_text: str):
        """
        Create a repeating reminder.
        It is not recommended to create a repeating reminder that is under 5 minutes long.
        """
        calendar = Calendar()
        t_struct, parse_status = calendar.parse(duration)
        if parse_status == 0:
            await ctx.bot.say(":x: Invalid time format.")
            return

        dt = datetime.datetime(*t_struct[:6])

        # Get the repeating difference.
        diff = ceil((dt - datetime.datetime.utcnow()).total_seconds())

        if diff < 300:
            await ctx.bot.say(":x: Cannot create a repeating reminder with a time under 5 minutes.")
            return

        object = {
            "user_id": ctx.message.author.id,
            "channel_id": ctx.message.channel.id,
            "expiration": datetime.datetime.utcnow().timestamp() + diff,
            "content": reminder_text,
            "repeating": True,
            "repeat_time": diff,
            "reminder_id": await r.table("reminders").count().run(ctx.bot.rethinkdb.connection)
        }

        # Add it to the database.
        i = await r.table("reminders").insert(object).run(ctx.bot.rethinkdb.connection)

        await ctx.bot.say(":heavy_check_mark: Will start reminding you at `{}`, then every `{}` seconds after.."
                          .format(dt, diff))

    @remind.command(pass_context=True)
    async def cancel(self, ctx: Context, *, reminder_id: int):
        """
        Cancels one of your reminders.
        """
        reminder = await r.table("reminders")\
            .get_all(ctx.message.author.id, index="user_id") \
            .filter({"reminder_id": reminder_id}).run(self.bot.rethinkdb.connection)

        reminder = await self.bot.rethinkdb.to_list(reminder)
        if not reminder:
            await ctx.bot.say(":x: That reminder ID does not exist.")
            return

        # Delete the reminder from the DB.
        i = await r.table("reminders") \
            .get_all(ctx.message.author.id, index="user_id") \
            .filter({"reminder_id": reminder_id}).delete().run(self.bot.rethinkdb.connection)

        await ctx.bot.say(":heavy_check_mark: Deleted reminder.")

    @remind.command(pass_context=True, aliases=["list"])
    async def reminders(self, ctx: Context):
        """
        Shows your current reminders, and where they are.
        """
        headers = ["ID", "Time", "Content", "Where", "Repeating"]
        items = []

        reminders = await r.table("reminders") \
            .get_all(ctx.message.author.id, index="user_id") \
            .order_by(r.asc("expiration")) \
            .run(ctx.bot.rethinkdb.connection)

        for record in reminders:
            # Parse the record's timestamp into a datetime.
            dt = datetime.datetime.fromtimestamp(record["expiration"])
            # Truncate the content, if we should.
            content = record["content"]
            if len(content) >= 25:
                # Truncate the end of it with `...`
                content = content[:22] + "..."

            repeats = record.get("repeating", False)
            reminder_id = record.get("reminder_id", "??")

            # Resolve the channel and server.
            channel = ctx.bot.manager.get_channel(record["channel_id"])

            if channel is None:
                name = "Unknown"
            else:
                name = "{} -> #{}".format(channel.server.name, channel.name)
            if len(name) >= 30:
                name = name[:27] + "..."

            fmt = dt.strftime("%Y-%m-%dT%H:%M:%S")

            row = [reminder_id, fmt, content, name, str(repeats)]
            items.append(row)

        pages = paginate_table(items, headers)
        for page in pages:
            await ctx.bot.say(page)


def setup(bot):
    bot.add_cog(Reminders(bot))
