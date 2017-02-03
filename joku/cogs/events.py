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

        self.bot.manager.events[event] += 1

    async def on_message(self, message: discord.Message):
        # Simply log the message.
        return
        await self.bot.rdblog.log_message(message)

    async def on_typing(self, channel: discord.TextChannel, user: discord.User, when: datetime.datetime):
        return
        obb = {
            "t": "TYPING_START",
            "member_id": user.id,
            "channel_id": channel.id
        }
        await self.bot.rdblog.log(obb)

    async def on_message_delete(self, message: discord.Message):
        return
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
        return
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
        #await self.bot.rdblog.log(obb)

        i = await self.bot.database.get_event_message(member.guild, "bans", "`{member.name}` got **bent**")

        if not i:
            return

        channel, event_msg = i

        try:
            msg = safe_format(event_msg, **{
                "member": member,
                "server": member.guild,
                "channel": channel
            })
        except AttributeError as e:
            await channel.send(":x: Event message has error: `{}`".format(repr(e)))
            return

        await channel.send(msg)

    async def on_member_unban(self, guild: discord.Guild, member: discord.User):
        obb = {
            "t": "GUILD_BAN_REMOVE",
            "member_id": str(member.id),
            "member_name": member.name,
            "server_id": str(guild.id)
        }
        #await self.bot.rdblog.log(obb)

        i = await self.bot.database.get_event_message(guild, "unbans", "`{member.name}` got **unbent**")

        if not i:
            return

        channel, event_msg = i

        try:
            msg = safe_format(event_msg, **{
                "member": member,
                "server": guild,
                "channel": channel
            })
        except AttributeError as e:
            await channel.send(":x: Event message has error: `{}`".format(repr(e)))
            return

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
        #await self.bot.rdblog.log(obb)

        i = await self.bot.database.get_event_message(member.guild, "joins", "Welcome {member.name}!")

        if not i:
            return

        channel, event_msg = i

        try:
            msg = safe_format(event_msg, **{
                "member": member,
                "server": member.guild,
                "channel": channel
            })
        except AttributeError as e:
            await channel.send(":x: Event message has error: `{}`".format(repr(e)))
            return

        await channel.send(msg)

    async def on_member_remove(self, member: discord.Member):
        # Log it in the database.
        obb = {
            "t": "GUILD_MEMBER_REMOVE",
            "member_id": str(member.id),
            "member_name": member.name,
            "server_id": str(member.guild.id)
        }
        #await self.bot.rdblog.log(obb)

        i = await self.bot.database.get_event_message(member.guild, "leaves", "Bye {member.name}!")

        if not i:
            return

        channel, event_msg = i

        try:
            msg = safe_format(event_msg, **{
                "member": member,
                "server": member.guild,
                "channel": channel
            })
        except AttributeError as e:
            await channel.send(":x: Event message has error: `{}`".format(repr(e)))
            return

        await channel.send(msg)


def setup(bot: Jokusoramame):
    bot.add_cog(Events(bot))
