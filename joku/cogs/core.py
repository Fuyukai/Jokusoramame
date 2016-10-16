"""
Core commands.
"""
import inspect

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
            "shards": self.bot.manager.max_shards,
            "servers": sum(1 for _ in self.bot.manager.get_all_servers()),
            "members": sum(1 for _ in self.bot.manager.get_all_members()),
            "unique_members": self.bot.manager.unique_member_count,
            "channels": sum(1 for _ in self.bot.manager.get_all_channels()),
            "shard": self.bot.shard_id
        }

        await self.bot.say("Currently connected to `{servers}` servers, "
                           "with `{channels}` channels "
                           "and `{members}` members (`{unique_members}` unique) "
                           "across `{shards}` shards.\n\n"
                           "This is shard ID **{shard}**.".format(**tmp))

    @commands.command(pass_context=True)
    async def help(self, ctx, command: str = None):
        """
        Help command.
        """
        prefix = ctx.prefix

        if command is None:
            # List the commands.
            base = "**Commands:**\nUse `{}help <command>` for more information about each command.\n\n".format(prefix)
            for n, (name, cls) in enumerate(self.bot.cogs.items()):
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

            await self.bot.say(base)
        else:
            # Check if the command is in the commands dict.
            if command not in self.bot.commands:
                await self.bot.say(":x: This command does not exist.")
                return
            # Use the default HelpFormatter to construct a nice message.
            fmtted = self.bot.formatter.format_help_for(ctx, self.bot.commands[command])
            for page in fmtted:
                await self.bot.say(page)


def setup(bot: Jokusoramame):
    bot.add_cog(Core(bot))
