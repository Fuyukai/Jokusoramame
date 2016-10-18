"""
Core commands.
"""
import inspect

import asyncio
from discord.ext import commands
from discord.ext.commands import Command, CheckFailure

from joku.bot import Jokusoramame
from joku.redis import with_redis_cooldown


class Core(object):
    """
    Core command class.
    """

    def __init__(self, bot: Jokusoramame):
        self.bot = bot

    def can_run_recursive(self, ctx, command: Command):
        # Check if the command has a parent.
        if command.parent is not None:
            rec = self.can_run_recursive(ctx, command.parent)
            if not rec:
                return False

        try:
            can_run = command.can_run(ctx)
        except CheckFailure:
            return False
        else:
            return can_run

    @commands.command(pass_context=True)
    async def stats(self, ctx):
        """
        Shows stats about the bot.
        """
        tmp = {
            "shards": ctx.bot.manager.max_shards,
            "servers": sum(1 for _ in ctx.bot.manager.get_all_servers()),
            "members": sum(1 for _ in ctx.bot.manager.get_all_members()),
            "unique_members": ctx.bot.manager.unique_member_count,
            "channels": sum(1 for _ in ctx.bot.manager.get_all_channels()),
            "shard": ctx.bot.shard_id
        }

        await ctx.bot.say("Currently connected to `{servers}` servers, "
                          "with `{channels}` channels "
                          "and `{members}` members (`{unique_members}` unique) "
                          "across `{shards}` shards.\n\n"
                          "This is shard ID **{shard}**.".format(**tmp))

    @commands.command(pass_context=True)
    async def help(self, ctx, *, command: str = None):
        """
        Help command.
        """
        prefix = ctx.prefix

        if command is None:
            # List the commands.
            base = "**Commands:**\nUse `{}help <command>` for more information about each command.\n\n".format(prefix)
            for n, (name, cls) in enumerate(ctx.bot.cogs.items()):
                # Increment N, so we start at 1 index instead of 0.
                n += 1

                cmds = []

                # Get a list of commands on the cog.
                members = inspect.getmembers(cls)
                for cname, m in members:
                    if isinstance(m, Command):
                        # Check if the author can run the command.
                        try:
                            if self.can_run_recursive(ctx, m):
                                cmds.append("`" + m.name + "`")
                        except CheckFailure:
                            pass

                base += "**{}. {}: ** {}\n".format(n, name, ' '.join(cmds) if cmds else "`No commands available to "
                                                                                        "you.`")

            await ctx.bot.say(base)
        else:
            # Check if the command is in the commands dict.
            # TODO: Allow subcommand checking
            if command not in ctx.bot.commands:
                await ctx.bot.say(":x: This command does not exist.")
                return
            # Use the default HelpFormatter to construct a nice message.
            fmtted = ctx.bot.formatter.format_help_for(ctx, ctx.bot.commands[command])
            for page in fmtted:
                await ctx.bot.say(page)


def setup(bot: Jokusoramame):
    bot.add_cog(Core(bot))
