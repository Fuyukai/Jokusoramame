"""
Core commands.
"""
import inspect

import aiohttp
import asyncio
import discord
import json

import threading

import tabulate
from discord.ext import commands
from discord.ext.commands import Command, CheckFailure
import psutil
from discord.ext.commands.bot import _default_help_command

from joku.bot import Jokusoramame, Context
from joku.checks import is_owner
from joku.cogs._common import Cog


class Core(Cog):
    """
    Core command class.
    """

    def __init__(self, bot: Jokusoramame):
        super().__init__(bot)

        self._is_loaded = False

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
    @commands.check(is_owner)
    async def shards(self, ctx: Context):
        """
        Shows shard status.
        """
        headers = ["Thread", "Status", "Servers", "Members"]
        items = []

        for (thread_id, thread), bot in zip(ctx.bot.manager.threads.items(), ctx.bot.manager.bots.values()):
            assert isinstance(thread, threading.Thread)
            if thread.is_alive():
                items.append((thread_id, "Alive", len(bot.servers), len(list(bot.get_all_members()))))
            else:
                items.append((thread_id, "Dead", 0, 0))

        tbl = tabulate.tabulate(items, headers, tablefmt="orgtbl")
        await ctx.bot.say("```{}```".format(tbl))

    @shards.command(pass_context=True)
    async def kill(self, ctx: Context, shard_id: int):
        """
        Kills a bot, by forcing it to logout.
        """
        bot = ctx.bot.manager.bots.get(shard_id)
        loop = bot.loop

        await ctx.bot.type()

        fut = asyncio.run_coroutine_threadsafe(bot.logout(), loop)
        await ctx.bot.say(":heavy_check_mark: Rebooting shard `{}`.".format(shard_id))

    @commands.command(pass_context=True)
    @commands.check(is_owner)
    async def changename(self, ctx: Context, *, name: str):
        """
        Changes the current username of the bot.

        This command is only usable by the owner.
        """
        await self.bot.edit_profile(username=name)
        await self.bot.say(":heavy_check_mark: Changed username.")

    @commands.command(pass_context=True)
    async def info(self, ctx):
        """
        Shows botto info.
        """
        await ctx.bot.say(":exclamation: **See <https://github.com/SunDwarf/Jokusoramame>, "
                          "or join the server at https://discord.gg/uQwVat8.**")

    @commands.command(pass_context=True)
    async def invite(self, ctx):
        invite = discord.utils.oauth_url(ctx.bot.app_id)
        await ctx.bot.say("**To invite the bot to your server, use this link: {}**".format(invite))

    @commands.command(pass_context=True)
    async def stats(self, ctx):
        """
        Shows stats about the bot.
        """
        current_process = psutil.Process()

        tmp = {
            "shards": ctx.bot.manager.max_shards,
            "servers": sum(1 for _ in ctx.bot.manager.get_all_servers()),
            "members": sum(1 for _ in ctx.bot.manager.get_all_members()),
            "unique_members": ctx.bot.manager.unique_member_count,
            "channels": sum(1 for _ in ctx.bot.manager.get_all_channels()),
            "shard": ctx.bot.shard_id,
            "memory": (current_process.memory_info().rss / 1024 // 1024)
        }

        await ctx.bot.say("Currently connected to `{servers}` servers, "
                          "with `{channels}` channels "
                          "and `{members}` members (`{unique_members}` unique) "
                          "across `{shards}` shards.\n"
                          "Currently using **{memory}MB** of memory\n\n"
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
                    base += "**{}. {}: ** {}\n".format(counter, name, ' '.join(cmds))
                    # Increment the counter here.
                    # Why? We don't want to increment it if the user can't use that cog.
                    counter += 1

            await ctx.bot.say(base)
        else:
            # Use the default help command.
            await _default_help_command(ctx, *command.split(" "))


def setup(bot: Jokusoramame):
    bot.add_cog(Core(bot))
