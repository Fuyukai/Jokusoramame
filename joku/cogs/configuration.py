"""
Configuration cog.
"""
import argparse
import shlex

import rethinkdb as r
from discord.ext import commands
from discord.ext.commands import MemberConverter, BadArgument, TextChannelConverter

from joku.bot import Jokusoramame, Context
from joku.cogs._common import Cog
from joku.rethink import RethinkAdapter
from joku.checks import has_permissions


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # raise the exception instead of printing it
        raise Exception(message)


class Config(Cog):
    # TODO: Add more events
    VALID_EVENTS = (
        "joins",
        "leaves",
        "bans",
        "unbans",
    )

    @commands.group(pass_context=True, invoke_without_command=True)
    @has_permissions(manage_server=True)
    async def notifications(self, ctx: Context):
        """
        Allows you to edit which events you are subscribed to on this bot.
        """
        welcome_setting = await ctx.bot.database.get_setting(ctx.message.guild, "events")

        if welcome_setting is None:
            await ctx.channel.send("Your server's notification settings is **off**.")
            return

        # Check the enabled dict.
        enabled = welcome_setting.get("events", {})
        if not any(enabled.values()):
            features = "none"
        else:
            features = ", ".join(name for name in enabled.keys() if enabled[name])

        await ctx.channel.send("Current events subscribed to: **{}**.".format(features))

    @notifications.command(pass_context=True, aliases=["sub"])
    async def subscribe(self, ctx: Context, *, event: str = None):
        """
        Subscribes to an event.
        To get a list of valid events, call this command without an argument.
        """
        if event is None:
            await ctx.channel.send("Valid events are: `{}`".format("`, `".join(self.VALID_EVENTS)))
            return

        # Add an "s" to the end of the event.
        if not event.endswith("s"):
            event += "s"

        if event not in self.VALID_EVENTS:
            await ctx.channel.send(":x: That event is not a valid event.")
            return

        # Add it to the events dict.
        d = await self.bot.database.get_setting(ctx.message.guild, "events")
        # Below, we use the channel ID as it is truthy.
        # It also signifies what channel to spam for the events.
        if not d:
            # Setting doesn't exist, create a new dict which has the event in it.
            d = {"events": {event: str(ctx.message.channel.id)}}
        else:
            # Setting does exist, make a new dict, and then flip the setting bool.
            d = {"events": d["events"]}
            d["events"][event] = str(ctx.message.channel.id)

        await ctx.bot.database.set_setting(ctx.message.guild, setting_name="events", value=d)
        await ctx.channel.send(":heavy_check_mark: Subscribed to event.")

    @notifications.command(pass_context=True, aliases=["unsub"])
    async def unsubscribe(self, ctx: Context, *, event: str = None):
        """
        Unsubscribe from an event that was subscribed in with `notifications subscribe`.
        """
        if event is None:
            await ctx.channel.send("Valid events are: `{}`".format("`, `".join(self.VALID_EVENTS)))
            return

        # Add an "s" to the end of the event.
        if not event.endswith("s"):
            event += "s"

        if event not in self.VALID_EVENTS:
            await ctx.channel.send(":x: That event is not a valid event.")
            return

        d = await ctx.bot.database.get_setting(ctx.message.guild, "events")
        if not d:
            # No need to unsub.
            await ctx.channel.send(":heavy_check_mark: Unsubscribed from event.")
            return

        # Edit the event.
        if 'events' not in d:
            d['events'] = {}

        d['events'][event] = False
        await ctx.bot.database.set_setting(ctx.message.guild, setting_name="events", value=d)
        await ctx.channel.send(":heavy_check_mark: Unsubscribed from event.")

    @notifications.command(pass_context=True)
    async def msg(self, ctx: Context, event: str, *, msg: str=None):
        """
        Allows editing the message sent for each event.
        """
        if not event.endswith("s"):
            event += "s"

        if event not in self.VALID_EVENTS:
            await ctx.channel.send(":x: That is not a valid event.")
            return

        if msg:
            d = {
                "event": event,
                "msg": msg
            }
            await ctx.bot.database.set_setting(ctx.message.guild, setting_name="event_message", value=d)
            await ctx.channel.send(":heavy_check_mark: Updated message for event `{}` to `{}`.".format(event, msg))

        else:
            _, msg = await ctx.bot.database.get_event_message(ctx.message.guild, event)
            if msg is None:
                await ctx.channel.send("**There is no custom message set for this event.**")
            else:
                await ctx.channel.send("The custom message for this event is: `{}`".format(msg))

    @commands.command(pass_context=True)
    @has_permissions(manage_server=True, manage_messages=True)
    async def inviscop(self, ctx: Context, *, status: str=None):
        """
        Manages the Invisible cop

        The Invisible Cop automatically deletes any messages of users with Invisible on.
        """
        if status is None:
            # Check the status.
            setting = await ctx.bot.database.get_setting(ctx.message.guild, "dndcop", {})
            if setting.get("status") == 1:
                await ctx.channel.send("Invis Cop is currently **on.**")
            else:
                await ctx.channel.send("Invis Cop is currently **off.**")
        else:
            if status.lower() == "on":
                await ctx.bot.database.set_setting(ctx.message.guild, "dndcop", status=1)
                await ctx.channel.send(":heavy_check_mark: Turned Invis Cop on.")
                return
            elif status.lower() == "off":
                await ctx.bot.database.set_setting(ctx.message.guild, "dndcop", status=0)
                await ctx.channel.send(":heavy_check_mark: Turned Invis Cop off.")
                return
            else:
                await ctx.channel.send(":x: No.")

    @commands.command(pass_context=True)
    @has_permissions(manage_server=True, manage_roles=True)
    async def rolestate(self, ctx: Context, *, status: str=None):
        """
        Manages rolestate.

        This will automatically save roles for users who have left the server.
        """
        if status is None:
            # Check the status.
            setting = await ctx.bot.database.get_setting(ctx.message.guild, "rolestate", {})
            if setting.get("status") == 1:
                await ctx.channel.send("Rolestate is currently **on.**")
            else:
                await ctx.channel.send("Rolestate is currently **off.**")
        else:
            if status.lower() == "on":
                await ctx.bot.database.set_setting(ctx.message.guild, "rolestate", status=1)
                await ctx.channel.send(":heavy_check_mark: Turned Rolestate on.")
                return
            elif status.lower() == "off":
                await ctx.bot.database.set_setting(ctx.message.guild, "rolestate", status=0)
                await ctx.channel.send(":heavy_check_mark: Turned Rolestate off.")
                return
            else:
                await ctx.channel.send(":x: No.")

    @commands.command(pass_context=True)
    @has_permissions(manage_server=True, manage_channels=True)
    async def ignore(self, ctx: Context, *, args: str = None):
        """
        Adds an ignore rule to the bot.
        This allows ignoring of commands or levelling in this channel or server.

        Settings are persistent - i.e your settings will not disappear when the bot leaves the server.
        """
        # Construct the program name.
        p_name = ctx.prefix + ctx.invoked_with
        parser = ArgumentParser(prog=p_name, add_help=False, formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument("-a", "--add",
                            help="Adds an ignore action.",
                            action="store_true")
        parser.add_argument("-r", "--remove",
                            help="Removes an ignore action.",
                            action="store_true")
        parser.add_argument("--type",
                            help="Defines what type of ignore to add. Valid choices are: 'commands' 'levels'")
        parser.add_argument("--target",
                            help="Defines the target of this action. You can mention a channel or a user.")

        if args is None:
            # Print the help text.
            h = parser.format_help()
            await ctx.channel.send("```{}```".format(h))
            return

        try:
            args = parser.parse_args(shlex.split(args))
        except Exception as e:
            await ctx.channel.send(":x: {}".format(' '.join(e.args)))
            return

        if args.type not in ['commands', 'levels']:
            await ctx.channel.send(":x: That is not a valid type.")
            return

        # Try to convert the target.
        try:
            converted = MemberConverter(ctx, args.target).convert()
        except BadArgument:
            try:
                converted = TextChannelConverter(ctx, args.target).convert()
            except BadArgument:
                await ctx.channel.send(":x: Target was invalid or could not be found.")
                return

        # If it's a remove, try and remove it.
        if args.remove:
            # Try and get the ignore rule that is currently in the database.
            # This means filtering by name and type.
            query = await r.table("settings") \
                .get_all(ctx.message.guild.id, index="server_id") \
                .filter({
                            "name": "ignore", "target": converted.id,
                            "type": args.type
                            }) \
                .run(ctx.bot.database.connection)

            got = await ctx.bot.database.to_list(query)
            if not got:
                await ctx.channel.send(":x: This item does not have an ignore rule on it of that type.")
                return

            # Remove the rule.
            await r.table("settings").get(got[0]["id"]).delete().run(ctx.bot.database.connection)
            await ctx.channel.send(":heavy_check_mark: Removed ignore rule.")
            return
        elif args.add:
            # Check if the rule already exists.
            query = await r.table("settings") \
                .get_all(ctx.message.guild.id, index="server_id") \
                .filter({
                            "name": "ignore", "target": converted.id,
                            "type": args.type
                            }) \
                .run(ctx.bot.database.connection)

            got = await self.bot.database.to_list(query)
            if got:
                await ctx.channel.send(":x: This item already has a rule with that target.")
                return

            # Add the rule.
            built_dict = {
                "server_id": ctx.message.guild.id, "name": "ignore",
                "target": converted.id, "type": args.type
                }

            result = await r.table("settings").insert(built_dict).run(self.bot.database.connection)
            await ctx.channel.send(":heavy_check_mark: Added ignore rule.")


def setup(bot):
    bot.add_cog(Config(bot))
