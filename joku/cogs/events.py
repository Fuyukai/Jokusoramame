"""
Cog that handles event listeners and such.
"""
import datetime
from math import floor

import collections
import discord
import time
import logbook
from discord.ext.commands import Command

import rethinkdb as r
from discord.ext import commands
import tabulate

from joku.bot import Jokusoramame, Context
from joku.checks import is_owner
from joku.cogs._common import Cog
from joku.vendor.safefmt import safe_format

unknown_events = {
    11: "HEARTBEAT_ACK",
    10: "READY",
    9: "INVALIDATE_SESSION",
    7: "RECONNECT"
}


class Events(Cog):
    def __init__(self, bot):
        super().__init__(bot)

        self.gw_logger = logbook.Logger("discord.gateway:shard-{}".format(self.bot.shard_id))

        self.current_commands = collections.deque(maxlen=20)

    async def on_command(self, ctx: Context):
        """
        Called when a command is ran.
        """
        d = {
            "ctx": ctx,
            "command": ctx.command  ,
            "timestamp": datetime.datetime.utcnow()
        }
        self.current_commands.append(d)

    @commands.command(pass_context=True)
    async def backlog(self, ctx: Context):
        """
        Show the most recent 20 commands.
        """
        fmt = ""
        for command in self.current_commands:
            fmt += "[{ctx.message.guild.name}][{ctx.message.channel.name}]: " \
                   "[{ctx.message.author.name}] -> [{ctx.invoked_with}]\n".format(ctx=command["ctx"])

        await ctx.channel.send(fmt, use_codeblocks=True)

    @commands.group(pass_context=True, invoke_without_command=True)
    async def events(self, ctx: Context):
        """
        Shows the top 10 most frequent events.
        """
        headers = ("Event", "Frequency")
        data = ctx.bot.manager.events.most_common(10)

        table = tabulate.tabulate(data, headers=headers, tablefmt="orgtbl")

        await ctx.channel.send("```{}```".format(table))

    @events.command(pass_context=True)
    @commands.check(is_owner)
    async def all(self, ctx: Context):
        """
        Shows all events the bot has received since it started logging.
        """
        message = await ctx.channel.send(":hourglass: Loading events... (this may take some time!)")
        time_before = time.time()
        # This abuses RethinkDB to count the events.
        q = await r.table("events") \
            .group("t") \
            .count() \
            .run(ctx.bot.rdblog.connection)

        # Get a list of events.
        l = list(q.items())
        # Sort them by the second key, and tabulate them.
        l = reversed(sorted(l, key=lambda x: x[1]))

        headers = ("Event", "Frequency")
        table = tabulate.tabulate(l, headers=headers, tablefmt="orgtbl")
        time_after = time.time()

        await message.edit("```{}```\n**Took {} seconds.**".format(table, floor(time_after - time_before)))

    @events.command(pass_context=True)
    @commands.check(is_owner)
    async def clean(self, ctx: Context):
        """
        Removes all PRESCENCE_UPDATE events from the log.

        This can take multiple hours to clean.
        """
        await ctx.channel.send(":hourglass: Cleaning...")
        coro = r.table("events") \
            .filter({"t": "PRESENCE_UPDATE"}) \
            .delete() \
            .run(ctx.bot.rdblog.connection)

        await coro
        await ctx.channel.send(":ok: Cleaned up.")

    @events.command(pass_context=True)
    async def seq(self, ctx: Context):
        """
        Shows the current sequence number.
        """
        seq = ctx.bot.connection.sequence
        await ctx.channel.send("Current sequence number: `{}`".format(seq))

    async def on_socket_response(self, data: dict):
        """
        Adds events to the event counter.
        """
        event = data.get("t")
        if not event:
            event = unknown_events.get(data.get("op"))
            if not event:
                self.bot.logger.warn("Caught None-event: `{}` ({})".format(event, data))

        # self.gw_logger.info("[{}] {}".format(event, data.get("d", {})))

        if event == "PRESENCE_UPDATE":
            # Manually format this event here.
            e_data = {
                "t": "PRESENCE_UPDATE",
                "server_id": data["d"].get("guild_id", None),
                "member_id": data["d"].get("user", None).get("id", None),
                "game": data["d"].get("game")
            }
            await self.bot.rdblog.log(e_data)

        elif event == "HEATBEAT_ACK":
            e_data = {
                "t": "HEARTBEAT_ACK",
                "seq": self.bot.connection.sequence
            }
            await self.bot.rdblog.log(e_data)

        self.bot.manager.events[event] += 1

    async def on_message(self, message: discord.Message):
        # Simply log the message.
        await self.bot.rdblog.log_message(message)

    async def on_typing(self, channel: discord.TextChannel, user: discord.User, when: datetime.datetime):
        obb = {
            "t": "TYPING_START",
            "member_id": user.id,
            "channel_id": channel.id
        }
        await self.bot.rdblog.log(obb)

    async def on_message_delete(self, message: discord.Message):
        obb = {
            "t": "MESSAGE_DELETE",
            "member_id": str(message.author.id),
            "member_name": str(message.author.name),
            "server_id": str(message.guild.id),
            "channel_id": str(message.guild.id),
            "content": str(message.content)
        }
        await self.bot.rdblog.log(obb)

    async def on_message_edit(self, old: discord.Message, message: discord.Message):
        obb = {
            "t": "MESSAGE_UPDATE",
            "member_id": str(message.author.id),
            "member_name": message.author.name,
            "server_id": str(message.guild.id),
            "channel_id": str(message.channel.id),
            "old_content": old.content,
            "content": message.content
        }
        await self.bot.rdblog.log(obb)

    async def on_member_ban(self, member: discord.Member):
        obb = {
            "t": "GUILD_BAN_ADD",
            "member_id": str(member.id),
            "member_name": member.name,
            "server_id": str(member.guild.id)
        }
        await self.bot.rdblog.log(obb)

        i = await self.bot.rethinkdb.get_event_message(member.guild, "bans", "`{member.name}` got **bent**")

        if not i:
            return

        channel, event_msg = i

        msg = safe_format(event_msg, **{
            "member": member,
            "server": member.guild,
            "channel": channel
        })
        await channel.send(msg)

    async def on_member_unban(self, guild: discord.Guild, member: discord.User):
        obb = {
            "t": "GUILD_BAN_REMOVE",
            "member_id": str(member.id),
            "member_name": member.name,
            "server_id": str(guild.id)
        }
        await self.bot.rdblog.log(obb)

        i = await self.bot.rethinkdb.get_event_message(guild, "unbans", "`{member.name}` got **unbent**")

        if not i:
            return

        channel, event_msg = i

        msg = safe_format(event_msg, **{
            "member": member,
            "server": guild,
            "channel": channel
        })
        await channel.send(msg)

    async def on_member_join(self, member: discord.Member):
        """
        Called when a member joins.

        Checks if this server is subscribed to joins, and formats the welcome message as appropriate.
        """

        # Log it in the database.
        obb = {
            "t": "GUILD_MEMBER_ADD",
            "member_id": str(member.id),
            "member_name": member.name,
            "server_id": str(member.guild.id)
        }
        await self.bot.rdblog.log(obb)

        i = await self.bot.rethinkdb.get_event_message(member.guild, "joins", "Welcome {member.name}!")

        if not i:
            return

        channel, event_msg = i

        msg = safe_format(event_msg, **{
            "member": member,
            "server": member.guild,
            "channel": channel
        })
        await channel.send(msg)

    async def on_member_remove(self, member: discord.Member):
        # Log it in the database.
        obb = {
            "t": "GUILD_MEMBER_REMOVE",
            "member_id": str(member.id),
            "member_name": member.name,
            "server_id": str(member.guild.id)
        }
        await self.bot.rdblog.log(obb)

        i = await self.bot.rethinkdb.get_event_message(member.guild, "leaves", "Bye {member.name}!")

        if not i:
            return

        channel, event_msg = i

        msg = safe_format(event_msg, **{
            "member": member,
            "server": member.guild,
            "channel": channel
        })
        await channel.send(msg)


def setup(bot: Jokusoramame):
    bot.add_cog(Events(bot))
