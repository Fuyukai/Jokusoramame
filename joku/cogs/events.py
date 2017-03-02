"""
Cog that handles event listeners.
"""
import typing

import discord
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import has_permissions, mod_command
from joku.vendor.safefmt import safe_format


class Events(Cog):
    VALID_EVENTS = (
        "joins",
        "leaves",
        "emojis"
    )

    async def on_member_join(self, member: discord.Member):
        """
        Called when a member joins.
        """
        event = await self.bot.database.get_event_setting(member.guild, "joins")
        if event is None:
            return

        # check if enabled
        if not event.enabled:
            return

        channel = member.guild.get_channel(event.channel_id)
        if not channel:
            # bad guild admins
            return

        fmt = {
            "server": member.guild,
            "member": member,
            "channel": channel
        }
        msg = safe_format(event.message or "Welcome {member.name} to {server.name}!", **fmt)
        await channel.send(msg)

    async def on_member_remove(self, member: discord.Member):
        event = await self.bot.database.get_event_setting(member.guild, "leaves")
        if event is None:
            return

        # check if enabled
        if not event.enabled:
            return

        channel = member.guild.get_channel(event.channel_id)
        if not channel:
            # bad guild admins
            return

        fmt = {
            "server": member.guild,
            "member": member,
            "channel": channel
        }
        msg = safe_format(event.message or "Bye {member.name}!", **fmt)
        await channel.send(msg)

    async def on_guild_emojis_update(self, before: typing.Sequence[discord.Emoji],
                                     after: typing.Sequence[discord.Emoji]):

        emoji = (before + after)[0]
        event = await self.bot.database.get_event_setting(emoji.guild, "emojis")
        if event is None:
            return

        # check if enabled
        if not event.enabled:
            return

        channel = emoji.guild.get_channel(event.channel_id)
        if not channel:
            # bad guild admins
            return

        fmt = {
            "server": emoji.guild,
            "channel": channel
        }
        msg = safe_format(event.message or "the emojis were updated")
        await channel.send(msg)

    @commands.group(invoke_without_command=True)
    @has_permissions(manage_guild=True)
    @mod_command()
    async def notifications(self, ctx: Context):
        """
        Manages your notifications setting for this server.

        You can either subscribe to notifications with `subscribe event`, unsubscribe with `unsubscribe event`,
        change the message with `msg event <msg>`, or move the channel with `move`.

        All commands here require manage_guild.
        """
        events = await ctx.bot.database.get_enabled_events(ctx.guild)

        fmt = ", ".join(events)
        await ctx.send("**Currently enabled events for this guild:** {}".format(fmt))

    @notifications.command()
    @has_permissions(manage_guild=True)
    @mod_command()
    async def subscribe(self, ctx: Context, event: str):
        """
        Subscribes to an event, enabling notifications for it.
        """
        if event not in self.VALID_EVENTS:
            await ctx.send(":x: That is not a valid event. Valid events: {}".format(", ".join(self.VALID_EVENTS)))
            return

        await ctx.bot.database.update_event_setting(ctx.guild, event,
                                                    enabled=True, channel=ctx.channel)
        await ctx.send(":heavy_check_mark: Subscribed to event.")

    @notifications.command()
    @has_permissions(manage_guild=True)
    @mod_command()
    async def unsubscribe(self, ctx: Context, event: str):
        """
        Unsubscribes from an event, disabling notifications from it.
        """
        events = await ctx.bot.database.get_enabled_events(ctx.guild)
        if event not in events:
            await ctx.send(":x: You are not subscribed to this event.")
            return

        await ctx.bot.database.update_event_setting(ctx.guild, event,
                                                    enabled=False)
        await ctx.send(":heavy_check_mark: Unsubscribed from event.")

    @notifications.command()
    @has_permissions(manage_guild=True)
    @mod_command()
    async def msg(self, ctx: Context, event: str, *, msg: str = None):
        """
        Updates the message for an event.

        If no message is provided, this will show the current message.
        """
        events = await ctx.bot.database.get_enabled_events(ctx.guild)
        if event not in events:
            await ctx.send(":x: You are not subscribed to this event.")
            return

        if msg is None:
            es = await ctx.bot.database.get_event_setting(event)
            await ctx.send("The current message for this event is: `{}`".format(es))
            return

        await ctx.bot.database.update_event_setting(ctx.guild, event,
                                                    message=msg)
        await ctx.send(":heavy_check_mark: Updated event message.")


setup = Events.setup
