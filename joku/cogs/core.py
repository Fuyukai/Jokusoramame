"""
Core commands.
"""
import asyncio
import datetime
import inspect
import json
import os
import platform

import aiohttp
import discord
import git
import psutil
import tabulate
from discord.ext import commands
from discord.ext.commands import CheckFailure, Command
from discord.ext.commands.bot import _default_help_command

from joku import VERSION
from joku.cogs._common import Cog
from joku.core.bot import Context, Jokusoramame
from joku.core.checks import is_owner, md_check
from joku.core.commands import DoNotRun


class Core(Cog):
    """
    Core command class.
    """

    def __init__(self, bot: Jokusoramame):
        super().__init__(bot)

        self._is_loaded = False

    async def on_channel_create(self, channel: discord.TextChannel):
        if channel.guild is None:
            return

        perms = channel.permissions_for(channel.guild.me)
        if not perms.send_messages and perms.read_messages:
            return

        await channel.send("first")

    async def ready(self):
        if self.bot.shard_id != 0:
            return

        if self._is_loaded:
            return

        self._is_loaded = True

        # Start the Discord Bots stats uploader.
        with aiohttp.ClientSession() as sess:
            while True:
                try:
                    token = self.bot.config.get("dbots_token", None)
                    if not token:
                        self.bot.logger.error("Cannot get token.")
                        return

                    # Make a POST request.
                    headers = {
                        "Authorization": token,
                        "User-Agent": "Jokusoramame - Powered by Python 3",
                        "X-Fuck-Meew0": "true",
                        "Content-Type": "application/json"
                    }
                    body = {
                        "server_count": str(sum(1 for server in self.bot.guilds))
                    }

                    url = "https://bots.discord.pw/api/bots/{}/stats".format(self.bot.user.id)

                    async with sess.post(url, headers=headers, data=json.dumps(body)) as r:
                        if r.status != 200:
                            self.bot.logger.error("Failed to update server count.")
                            self.bot.logger.error(await r.text())
                        else:
                            self.bot.logger.info("Updated server count on bots.discord.pw.")
                except:
                    self.bot.logger.exception()
                finally:
                    await asyncio.sleep(15)

    def can_run_recursive(self, ctx, command: Command):
        try:
            can_run = command.can_run(ctx)
        except CheckFailure:
            return False
        else:
            return can_run

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def kill(self, ctx: Context):
        """
        Kills the bot.
        """
        await ctx.channel.send(":heavy_check_mark: Killing bot.")
        ctx.bot.loop.create_task(ctx.bot.logout())

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def changename(self, ctx: Context, *, name: str):
        """
        Changes the current username of the bot.

        This command is only usable by the owner.
        """
        await ctx.bot.user.edit(username=name)
        await ctx.channel.send(":heavy_check_mark: Changed username.")

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def changeavy(self, ctx: Context, *, url: str):
        """
        Changes the current avatar of the bot.

        This command is only usable by the owner.
        """
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url) as f:
                body = await f.read()

                await ctx.bot.user.edit(avatar=body)

        await ctx.channel.send(":heavy_check_mark: Changed avatar.")

    @commands.command(pass_context=True)
    async def info(self, ctx: Context):
        """
        Shows botto info.
        """
        repo = git.Repo()
        curr_branch = repo.active_branch
        commits = list(repo.iter_commits(curr_branch, max_count=3))

        memory_usage = psutil.Process().memory_full_info().uss / 1024 ** 2

        me = ctx.message.guild.me  # type: discord.Member

        d = "**Git Log:**\n"
        for commit in commits:
            d += "[`{}`](https://github.com/SunDwarf/Jokusoramame/commit/{}) {}\n".format(
                commit.hexsha[len(commit.hexsha) - 6:len(commit.hexsha)],
                commit.hexsha,
                commit.message.split("\n")[0]
            )

        owner = ctx.bot.get_member(ctx.bot.owner_id)  # type: discord.Member

        embed = discord.Embed(description=d)
        embed.set_author(name=str(owner), icon_url=owner.avatar_url)

        embed.colour = me.colour

        embed.url = ctx.bot.invite_url
        embed.title = "Add the bot to your server"
        embed.description = "[Join the server](https://discord.gg/uQwVat8)\n{}".format(d)

        # Add the required fields.
        embed.add_field(name="Shards", value=ctx.bot.shard_count)
        embed.add_field(name="Memory usage", value="{:.2f} MiB".format(memory_usage))
        embed.add_field(name="Version", value=VERSION)

        embed.add_field(name="Servers", value=str(sum(1 for x in ctx.bot.guilds)))
        embed.add_field(name="Users", value=str(sum(1 for x in ctx.bot.get_all_members())))
        embed.add_field(name="Unique users", value=str(len(set(m.id for m in ctx.bot.get_all_members()))))

        embed.add_field(name="Python version", value=platform.python_version())
        embed.add_field(name="Hostname", value=platform.node())
        embed.add_field(name="discord.py version", value=discord.__version__)

        embed.set_footer(text="Powered by asyncio", icon_url=ctx.message.guild.me.avatar_url)
        embed.timestamp = datetime.datetime.utcnow()

        await ctx.channel.send(embed=embed)

    @commands.command(pass_context=True)
    async def source(self, ctx: Context, *, command: str=None):
        """
        Shows the source code for a specific command.
        """
        source_url = 'https://github.com/SunDwarf/Jokusoramame'
        if command is None:
            await ctx.channel.send(source_url)
            return

        # copied from robo danno
        code_path = command.split(' ')
        obj = ctx.bot
        for cmd in code_path:
            try:
                obj = obj.get_command(cmd)
                if obj is None:
                    await ctx.channel.send(':x: No such command: `{}`'.format(cmd))
                    return
            except AttributeError:
                await ctx.channel.send(':x: `{.name}` command has no subcommands'.format(obj))
                return

        # Get the code object from the callback
        src = obj.callback.__code__
        lines, firstlineno = inspect.getsourcelines(src)
        if not obj.callback.__module__.startswith('joku'):
            await ctx.channel.send(":x: Cannot get source for non-bot items.")
            return

        # One of our commands.
        location = os.path.relpath(src.co_filename).replace('\\', '/')
        final_url = '{}/blob/master/{}#L{}-L{}'.format(source_url, location, firstlineno,
                                                         firstlineno + len(lines) - 1)
        await ctx.channel.send(final_url)

    @commands.command(pass_context=True, hidden=True)
    async def pong(self, ctx: Context, *, ip: str="8.8.8.8"):
        s = await asyncio.create_subprocess_exec("ping", *("{} -D -s 16 -i 0.2 -c 4".format(ip).split()),
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        async with ctx.channel.typing():
            stdout, stderr = await s.communicate()

        if stderr:
            fmt = "```{}```".format(stderr.decode())
        else:
            fmt = "```{}```".format(stdout.decode())
        await ctx.send(fmt)

    @commands.command(pass_context=True)
    async def invite(self, ctx: Context):
        await ctx.channel.send("**To invite the bot to your server, use this link: {}**".format(ctx.bot.invite_url))

    @commands.command(pass_context=True)
    async def help(self, ctx: Context, *, command: str = None):
        """
        Help command.
        """
        prefix = ctx.prefix

        if command is None:
            # List the commands.
            base = "**Commands:**\nUse `{}help <command>` " \
                   "for more information about each command.\n\n".format(prefix)

            if prefix.endswith("::"):
                base += "**This will only show moderation related commands.**\n\n"
            else:
                base += "**Use j::help to show moderation related commands.**\n\n"

            counter = 1
            for (name, cls) in ctx.bot.cogs.items():
                cmds = []

                # Get a list of commands on the cog, by inspecting the members for any Command
                #  instances.
                members = inspect.getmembers(cls)
                for cname, m in members:
                    if isinstance(m, Command):
                        if m.parent is not None:
                            # Construct a new name, using the parent name.
                            new_name = m.full_parent_name + " " + m.name
                        else:
                            new_name = m.name
                        # Check if the author can run the command.
                        try:
                            if prefix.endswith("::"):
                                if md_check not in m.checks:
                                    continue

                            if await m.can_run(ctx):
                                if not m.hidden:
                                    cmds.append("`" + new_name + "`")
                        except (CheckFailure, DoNotRun):
                            pass

                # Make sure the user can run any commands for this cog.
                if cmds:
                    base += "**{}. {}: ** {}\n".format(counter, name,
                                                       ' **|** '.join(reversed(sorted(cmds))))
                    # Increment the counter here.
                    # Why? We don't want to increment it if the user can't use that cog.
                    counter += 1
            await ctx.channel.send(base)
        else:
            # Use the default help command.
            await _default_help_command(ctx, *command.split(" "))

    def _get_uptime_text(self, start_time: int) -> str:
        # copied from robo danno
        now = datetime.datetime.utcnow()
        delta = now - datetime.datetime.fromtimestamp(start_time)
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        fmt = '{h}h {m}m {s}s'
        if days:
            fmt = '{d}d ' + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    @commands.command(pass_context=True)
    async def uptime(self, ctx: Context):
        """
        Shows the bot's uptime.
        """
        await ctx.channel.send(self._get_uptime_text(ctx.bot.startup_time))


def setup(bot: Jokusoramame):
    bot.add_cog(Core(bot))
