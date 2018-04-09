"""
Core plugin.
"""
import contextlib
import platform
import sys
import time
import traceback
from io import BytesIO, StringIO
from itertools import cycle

import asks
import asyncqlio
import curio
import curious
import git
import matplotlib.pyplot as plt
import numpy as np
import pkg_resources
import psutil
import tabulate
from asks.response_objects import Response
from curio import subprocess
from curio.thread import spawn_thread
from curious import Channel, Embed, EventContext, event
from curious.commands import Plugin, command, condition
from curious.commands.context import Context
from curious.commands.decorators import ratelimit
from curious.commands.ratelimit import BucketNamer
from curious.exc import HTTPException, PermissionsError

from jokusoramame.bot import Jokusoramame
from jokusoramame.utils import display_time, rgbize


def is_owner(ctx: Context):
    return ctx.author.id in [ctx.bot.application_info.owner.id, 214796473689178133, 396290259907903491]


class Core(Plugin):
    """
    Joku v2 core plugin.
    """

    @event("channel_create")
    async def first(self, ctx: EventContext, channel: Channel):
        if channel.guild_id is None:
            return

        try:
            await channel.messages.send("first")
        except PermissionsError:  # clobber
            pass

    @command()
    async def ping(self, ctx: Context):
        """
        Ping!
        """
        gw_latency = "{:.2f}".format(
            ctx.bot.gateways[ctx.guild.shard_id].heartbeat_stats.gw_time * 1000
        )
        fmt = f":ping_pong: Ping! | Gateway latency: {gw_latency}ms"

        before = time.monotonic()
        initial = await ctx.channel.messages.send(fmt)
        after = time.monotonic()
        fmt = fmt + f" | HTTP latency: {(after - before) * 1000:.2f}ms"
        await initial.edit(fmt)

    @command()
    async def pong(self, ctx: Context, *, location: str = "8.8.8.8"):
        """
        Pong!
        """
        async with ctx.channel.typing:
            words = location.split(" ")
            word = words[0]
            if word.startswith("-"):
                await ctx.channel.messages.send("No")
                return

            command = "ping {} -D -s 16 -i 0.2 -c 4".format(words[0])
            try:
                proc = await subprocess.run(command.split(),
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                result = e.stderr.decode()
            else:
                result = proc.stdout.decode()
                result += "\n" + proc.stderr.decode()

            await ctx.channel.messages.send(f"```joku@discord $ {command}\n{result}```")

    @command()
    async def uptime(self, ctx: Context):
        """
        Shows the bot's uptime.
        """
        seconds_booted = int(time.time() - psutil.Process().create_time())
        uptime_str = display_time(seconds_booted)
        await ctx.channel.messages.send(f"{uptime_str} (total: {int(seconds_booted)}s)")

    @command()
    @condition(is_owner)
    async def eval(self, ctx: Context, *, code: str):
        """
        Evaluates some code.
        """
        code = code.lstrip("`").rstrip("`")
        lines = code.split("\n")
        lines = ["    " + i for i in lines]
        lines = '\n'.join(lines)

        f_code = f"async def _():\n{lines}"
        stdout = StringIO()

        try:
            namespace = {
                "ctx": ctx,
                "message": ctx.message,
                "guild": ctx.message.guild,
                "channel": ctx.message.channel,
                "author": ctx.message.author,
                "bot": ctx.bot,
                **sys.modules
            }
            exec(f_code, namespace, namespace)
            func = namespace["_"]

            with contextlib.redirect_stdout(stdout):
                result = await func()

        except Exception as e:
            result = ''.join(traceback.format_exception(None, e, e.__traceback__))
        finally:
            stdout.seek(0)

        fmt = f"```py\n{stdout.read()}\n{result}\n```"
        await ctx.channel.messages.send(fmt)

    @command()
    @condition(is_owner)
    async def sql(self, ctx: Context, *, sql: str):
        """
        Executes some SQL.
        """
        before = time.monotonic()
        try:
            sess = ctx.bot.db.get_session()
            async with sess:
                cursor = await sess.cursor(sql)
                rows = await cursor.flatten()

        except Exception as e:
            await ctx.channel.messages.send(f"`{str(e)}`")
            return
        # get timings of the runtime
        after = time.monotonic()
        taken = after - before

        # TODO: Pagination
        if not rows:
            fmt = "```\nNo rows returned.\n\n"
        else:
            headers = rows[0].keys()
            values = [row.values() for row in rows]
            result = tabulate.tabulate(values, headers, tablefmt="orgtbl")
            fmt = f"```\n{result}\n\n"

        fmt += f"Query returned in {taken:.3f}s```"
        await ctx.channel.messages.send(fmt)

    @command()
    @condition(is_owner)
    async def changename(self, ctx: Context, *, name: str):
        """
        Changes the name of the bot.
        """
        await ctx.bot.user.edit(username=name)
        await ctx.channel.messages.send(":heavy_check_mark: Changed name.")

    @command()
    @condition(is_owner)
    async def changeavatar(self, ctx: Context, *, link: str):
        """
        Changes the name of the bot.
        """
        sess = asks.Session()
        resp: Response = await sess.get(link)
        if resp.status_code != 200:
            await ctx.channel.messages.send(f":x: Failed to download avatar. "
                                            f"(code: {resp.status_code})")
            return

        data = resp.raw
        try:
            await ctx.bot.user.edit(avatar=data)
        except HTTPException:
            await ctx.channel.messages.send(":x: Failed to edit avatar.")
            return

        await ctx.channel.messages.send(":heavy_check_mark: Changed avatar.")

    @command()
    async def info(self, ctx: Context):
        """
        Shows some quick info about the bot.
        """
        repo = git.Repo()
        curr_branch = repo.active_branch
        commits = list(repo.iter_commits(curr_branch, max_count=3))

        memory_usage = psutil.Process().memory_full_info().uss / 1024 ** 2
        d = "**Git Log:**\n"
        for commit in commits:
            d += "[`{}`](https://github.com/SunDwarf/Jokusoramame/commit/{}) {}\n".format(
                commit.hexsha[len(commit.hexsha) - 6:len(commit.hexsha)],
                commit.hexsha,
                commit.message.split("\n")[0]
            )

        d += "\n[Icon credit: @tofuvi](http://tofuvi.tumblr.com/)"

        em = Embed()
        em.title = "Jokusoramame v2! New! Improved!"
        em.description = d
        em.author.icon_url = ctx.bot.user.static_avatar_url
        em.author.name = ctx.bot.user.username
        em.colour = ctx.guild.me.colour if ctx.guild else 0x000000
        em.url = "https://www.youtube.com/watch?v=hgcLyZ3QYo8"

        em.add_field(name="Python", value=platform.python_version())
        em.add_field(name="curious", value=curious.__version__)
        em.add_field(name="asyncqlio", value=asyncqlio.__version__)

        em.add_field(name="curio", value=curio.__version__)
        em.add_field(name="asks", value=pkg_resources.get_distribution("asks").version)
        em.add_field(name="asyncpg", value=pkg_resources.get_distribution("asyncpg").version)

        em.add_field(name="Memory usage", value=f"{memory_usage:.2f} MiB")
        em.add_field(name="Servers", value=len(ctx.bot.guilds))
        em.add_field(name="Shards", value=ctx.event_context.shard_count)

        em.set_footer(text=f"香港快递 | Git branch: {curr_branch.name}")

        await ctx.channel.messages.send(embed=em)

    @command()
    @ratelimit(limit=1, time=60, bucket_namer=BucketNamer.GLOBAL)
    async def stats(self, ctx: Context):
        """
        Shows some bot stats.
        """
        palette = [0xabcdef, 0xbcdefa, 0xcdefab, 0xdefabc, 0xefabcd, 0xfabcde]
        palette = cycle(palette)

        async with ctx.channel.typing, spawn_thread():
            with ctx.bot._plot_lock:
                names, values = [], []
                for name, value in ctx.bot.events_handled.most_common():
                    names.append(name)
                    values.append(value)

                colours = rgbize([next(palette) for _ in names])

                y_pos = np.arange(len(names))
                plt.bar(y_pos, values, align='center', color=colours)
                plt.xticks(y_pos, names, rotation=90)
                plt.ylabel("Count")
                plt.xlabel("Event")
                plt.tight_layout()
                plt.title("Event stats")

                buf = BytesIO()
                plt.savefig(buf, format='png')
                plt.cla()
                plt.clf()

        buf.seek(0)
        data = buf.read()
        await ctx.channel.messages.upload(data, filename="stats.png")

    @command()
    @condition(is_owner)
    async def reload(self, ctx: Context, *, module_name: str):
        """
        Reloads a plugin.
        """
        bot: Jokusoramame = ctx.bot
        await bot.manager.unload_plugins_from(module_name)
        await bot.manager.load_plugins_from(module_name)
        await ctx.channel.messages.send(f":heavy_check_mark: Reloaded {module_name}.")

    @command(name="load")
    @condition(is_owner)
    async def _load(self, ctx: Context, *, module_name: str):
        """
        Loads a plugin.
        """
        bot: Jokusoramame = ctx.bot
        await bot.manager.load_plugins_from(module_name)
        await ctx.channel.messages.send(f":heavy_check_mark: Loaded {module_name}.")

    @command()
    @condition(is_owner)
    async def update(self, ctx):
        """
        Updates the bot from git.
        """
        try:
            proc = await subprocess.run('git pull'.split(),
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            result = e.stderr.decode()
        else:
            result = proc.stdout.decode()
            result += "\n" + proc.stderr.decode()

        await ctx.channel.messages.send(f"```\n{result}```")
