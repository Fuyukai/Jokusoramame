"""
Configuration cog.
"""
import argparse
import shlex

import rethinkdb as r
from discord.ext import commands
from discord.ext.commands import Context, MemberConverter, BadArgument, ChannelConverter

from joku.bot import Jokusoramame


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # raise the exception instead of printing it
        raise Exception(message)


class Config(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

    @commands.command(pass_context=True)
    @commands.has_permissions(manage_server=True, manage_channels=True)
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
            await ctx.bot.say("```{}```".format(h))
            return

        try:
            args = parser.parse_args(shlex.split(args))
        except Exception as e:
            await ctx.bot.say(":x: {}".format(' '.join(e.args)))
            return

        if args.type not in ['commands', 'levels']:
            await ctx.bot.say(":x: That is not a valid type.")
            return

        # Try to convert the target.
        try:
            converted = MemberConverter(ctx, args.target).convert()
        except BadArgument:
            try:
                converted = ChannelConverter(ctx, args.target).convert()
            except BadArgument:
                await ctx.bot.say(":x: Target was invalid or could not be found.")
                return

        # If it's a remove, try and remove it.
        if args.remove:
            # Try and get the ignore rule that is currently in the database.
            # This means filtering by name and type.
            query = await r.table("settings")\
                    .get_all(ctx.message.server.id, index="server_id")\
                    .filter({"name": "ignore", "target": converted.id,
                             "type": args.type})\
                    .run(ctx.bot.rethinkdb.connection)

            got = await ctx.bot.rethinkdb.to_list(query)
            if not got:
                await ctx.bot.say(":x: This item does not have an ignore rule on it of that type.")
                return

            # Remove the rule.
            await r.table("settings").get(got[0]["id"]).delete().run(ctx.bot.rethinkdb.connection)
            await ctx.bot.say(":heavy_check_mark: Removed ignore rule.")
            return
        elif args.add:
            # Check if the rule already exists.
            query = await r.table("settings")\
                    .get_all(ctx.message.server.id, index="server_id")\
                    .filter({"name": "ignore", "target": converted.id,
                             "type": args.type})\
                    .run(ctx.bot.rethinkdb.connection)

            got = await self.bot.rethinkdb.to_list(query)
            if got:
                await ctx.bot.say(":x: This item already has a rule with that target.")
                return

            # Add the rule.
            built_dict = {"server_id": ctx.message.server.id, "name": "ignore",
                          "target": converted.id, "type": args.type}

            result = await r.table("settings").insert(built_dict).run(self.bot.rethinkdb.connection)
            await ctx.bot.say(":heavy_check_mark: Added ignore rule.")



def setup(bot):
    bot.add_cog(Config(bot))
