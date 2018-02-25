import re
from io import BytesIO
from typing import Awaitable, List

import matplotlib.pyplot as plt
import seaborn as sns
from curio.thread import async_thread
from curious.commands import Context, Plugin
from curious.commands.decorators import autoplugin, ratelimit
from yapf.yapflib.style import CreatePEP8Style
from yapf.yapflib.yapf_api import FormatCode

code_regexp = re.compile(r"```([^\n]+)\n?(.+)\n?```", re.DOTALL)


@autoplugin
class Misc(Plugin):
    @ratelimit(limit=1, time=30)
    async def command_palette(self, ctx: Context, *, colours: List[int]):
        """
        Shows a palette plot.
        """
        pal_colours = []
        colours = colours[:12]  # limit to 12
        for colour in colours:
            rgb255 = ((colour >> 16) & 255, (colour >> 8) & 255, colour & 255)
            rgb100 = tuple(c / 255 for c in rgb255)
            pal_colours.append(rgb100)

        @async_thread
        def plot_palette() -> Awaitable[BytesIO]:
            with ctx.bot._plot_lock:
                sns.palplot(pal_colours, size=1)
                plt.tight_layout()  # remove useless padding

                buf = BytesIO()
                plt.savefig(buf, format="png")
                buf.seek(0)

                plt.clf()
                plt.cla()

                return buf

        @async_thread()
        def plot_dark_palette() -> Awaitable[BytesIO]:
            with ctx.bot._plot_lock:
                with plt.style.context("dark_background"):
                    sns.palplot(pal_colours, size=1)
                    plt.tight_layout()  # remove useless padding

                    buf = BytesIO()
                    plt.savefig(buf, format="png")
                    buf.seek(0)

                    plt.clf()
                    plt.cla()

                return buf

        if ctx.bot._plot_lock.locked():
            await ctx.channel.messages.send("Waiting for plot lock...")

        async with ctx.channel.typing:
            buf = await plot_palette()
            buf2 = await plot_dark_palette()

        await ctx.channel.messages.upload(fp=buf.read(), filename="plot.png")
        await ctx.channel.messages.upload(fp=buf2, filename="plot_dark.png")

    def _normalize_language(self, lang: str) -> str:
        """
        Normalizes a language name into consistency.
        """
        lang = lang.lower().rstrip("\n")
        print(repr(lang))
        if lang in ["py", "python", "py3k"]:
            return "python"

        return lang

    async def command_reformat(self, ctx: Context, *, message: str):
        """
        Reformats some code.
        """
        code_match = code_regexp.match(message)
        if code_match is None:
            return await ctx.channel.messages.send(":x: Could not find a valid code block with "
                                                   "language.")

        language, code = code_match.groups()
        code = code.replace("\t", "    ")
        language = self._normalize_language(language)

        if language == "python":
            # yapfify
            style = CreatePEP8Style()
            style['COLUMN_LIMIT'] = 100
            reformatted, changes = FormatCode(code, style_config=style)
            return await ctx.channel.messages.send(f"```py\n{reformatted}```")

        return await ctx.channel.messages.send(":x: Unknown language.")
