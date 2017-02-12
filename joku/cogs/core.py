"""
Core commands.
"""
import datetime
import inspect
import os
import platform

import aiohttp
import asyncio
import discord
import json

import threading

import git
import tabulate
from discord.ext import commands
from discord.ext.commands import Command, CheckFailure
import psutil
from discord.ext.commands.bot import _default_help_command

from joku import VERSION
from joku.bot import Jokusoramame, Context
from joku.checks import is_owner
from joku.cogs._common import Cog
from joku.manager import SingleLoopManager
from joku.threadmanager import ThreadManager


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
                    token = self.bot.manager.config.get("dbots_token", None)
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
                        "server_count": str(sum(1 for server in self.bot.manager.get_all_servers()))
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

    @commands.group(pass_context=True, invoke_without_command=True)
    async def shards(self, ctx: Context):
        """
        Shows shard status.
        """
        headers = ["Shard", "Servers", "Members"]
        items = []

        for bot_id, bot in ctx.bot.manager.bots.items():
            items.append((bot_id, len(bot.guilds), sum(1 for i in bot.get_all_members())))

        tbl = tabulate.tabulate(items, headers, tablefmt="orgtbl")
        await ctx.channel.send("```{}```".format(tbl))

    @shards.command(pass_context=True)
    @commands.check(is_owner)
    async def kill(self, ctx: Context, shard_id: int):
        """
        Kills a bot, by forcing it to logout.
        """
        bot = ctx.bot.manager.bots.get(shard_id)
        if not bot:
            await ctx.channel.send(":x: That shard does not exist.")

        await ctx.channel.send(":heavy_check_mark: Rebooting shard `{}`.".format(shard_id))
        if isinstance(ctx.bot.manager, ThreadManager):
            asyncio.run_coroutine_threadsafe(bot.logout(), bot.loop)
        else:
            bot.loop.create_task(bot.logout())

    @shards.command(pass_context=True)
    @commands.check(is_owner)
    async def restart(self, ctx: Context):
        """
        Forces a restart of all shards.
        """
        ctx.bot.manager.reload_config_file()

        await ctx.channel.send(":hourglass: Scheduling a reboot for all shards...")
        # This injects the task into the shards WITHOUT yielding to the event loop.
        for shard in ctx.bot.manager.bots.values():
            if isinstance(ctx.bot.manager, ThreadManager):
                asyncio.run_coroutine_threadsafe(shard.logout(), shard.loop)
            elif isinstance(ctx.bot.manager, SingleLoopManager):
                shard.loop.create_task(shard.logout())

        # Now we yield to the loop, and let it kill us.
        await asyncio.sleep(0)

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def reloadshard(self, ctx):
        """
        Reloads all modules for a shard.
        """
        # Reload the config file so that all cogs are ready.
        ctx.bot.manager.reload_config_file()

        # Reload this shard
        for extension in ctx.bot.extensions.copy():
            ctx.bot.unload_extension(extension)
            try:
                ctx.bot.load_extension(extension)
            except BaseException as e:
                ctx.bot.logger.exception()
            else:
                ctx.bot.logger.info("Reloaded {}.".format(extension))

        await ctx.channel.send(":heavy_check_mark: Reloaded shard.")

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def reloadall(self, ctx: Context):
        """
        Reloads all the modules for every shard.
        """
        #if not isinstance(ctx.bot.manager, SingleLoopManager):
        #    await ctx.channel.send(":x: Cannot reload all shards inside a ThreadManager.")
        #    return

        # Reload the config file.
        #ctx.bot.manager.reload_config_file()

        for extension in ctx.bot.extensions.copy():
            ctx.bot.unload_extension(extension)
            try:
                ctx.bot.load_extension(extension)
            except BaseException as e:
                ctx.bot.logger.exception()
            else:
                ctx.bot.logger.info("Reloaded {}.".format(extension))

        await ctx.channel.send(":heavy_check_mark: Reloaded bot.")

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

        embed.url = "https://discord.gg/uQwVat8"
        embed.title = "Official Server Invite"

        # Add the required fields.
        embed.add_field(name="Shards", value=ctx.bot.shard_count)
        embed.add_field(name="Memory usage", value="{:.2f} MiB".format(memory_usage))
        embed.add_field(name="Version", value=VERSION)

        embed.add_field(name="Servers", value=str(sum(1 for x in ctx.bot.guilds)))
        embed.add_field(name="Users", value=str(sum(1 for x in ctx.bot.get_all_members())))
        embed.add_field(name="Unique users", value=str(len(set(ctx.bot.get_all_members()))))

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

    @commands.command(pass_context=True)
    async def pong(self, ctx: Context):
        await ctx.channel.send("Fuck you")

    @commands.command(pass_context=True)
    async def invite(self, ctx):
        invite = discord.utils.oauth_url(ctx.bot.app_id)
        await ctx.channel.send("**To invite the bot to your server, use this link: {}**".format(invite))

    @commands.command(pass_context=True)
    async def help(self, ctx: Context, *, command: str = None):
        """
        Help command.
        """
        prefix = ctx.prefix

        if command is None:
            # List the commands.
            base = "**Commands:**\nUse `{}help <command>` for more information about each command.\n\n".format(prefix)
            counter = 1
            for (name, cls) in ctx.bot.cogs.items():
                cmds = []

                # Get a list of commands on the cog, by inspecting the members for any Command instances.
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
                            if self.can_run_recursive(ctx, m):
                                cmds.append("`" + new_name + "`")
                        except CheckFailure:
                            pass

                # Make sure the user can run any commands for this cog.
                if cmds:
                    base += "**{}. {}: ** {}\n".format(counter, name, ' **|** '.join(reversed(sorted(cmds))))
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

        em = discord.Embed(title="Uptime statistics")

        em.add_field(name="Bot Uptime", value=self._get_uptime_text(ctx.bot.manager.start_time))
        em.add_field(name="Shard Uptime", value=self._get_uptime_text(ctx.bot.startup_time))

        await ctx.channel.send(embed=em)


def setup(bot: Jokusoramame):
    bot.add_cog(Core(bot))
