import random
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

from jokusoramame.utils import rgbize

code_regexp = re.compile(r"```([^\n]+)\n?(.+)\n?```", re.DOTALL)

ADJECTIVES = {
    "Smithian ": 1,
    "Ricardian ": 1,
    "Randian ": 2,
    "Vegan ": 3,
    "Synthesist ": 3,
    "Green ": 6,
    "Insurrectionary ": 6,
    "Jewish ": 8,
    "Bolshevik ": 8,
    "Post-left ": 8,
    "Inclusive": 9,
    "Individualist ": 9,
    "Queer ": 10,
    "Atheist ": 10,
    "Liberal ": 10,
    "Libertarian ": 10,
    "Conservative ": 10,
    "Social ": 12,
    "Islamic ": 12,
    "Radical ": 12,
    "Catholic ": 12,
    "Esoteric ": 12,
    "Christian ": 12,
    "Progressive ": 12,
    "Post-Colonial ": 12,
    "Democratic ": 13,
    "": 30
}

PREFIXES = {
    "Alt-": 1,
    "Bio-": 1,
    "Post-": 3,
    "Anarcha-": 3,
    "Avant Garde ": 3,
    "Eco-": 4,
    "Communal ": 6,
    "Afro-": 8,
    "Ethno-": 8,
    "Ultra-": 8,
    "Neo-": 10,
    "Pan-": 10,
    "Anti-": 10,
    "Paleo-": 10,
    "Techno-": 10,
    "Market ": 10,
    "Revolutionary ": 10,
    "Crypto-": 12,
    "Anarcho-": 12,
    "National ": 12,
    "Orthodox ": 12,
    "": 40
}

IDEOLOGIES = {
    "Posadism": 1,
    "Kemalism": 2,
    "Distributism": 2,
    "Titoism": 3,
    "Putinism": 3,
    "Makhnovism": 3,
    "Georgism": 4,
    "Keynesian": 4,
    "Platformism": 4,
    "Municipalism": 5,
    "Confederalism": 5,
    "Egoism": 6,
    "Luddite": 6,
    "Agorism": 6,
    "Unionism": 6,
    "Thatcherite": 6,
    "Minarchism": 7,
    "Ba'athism": 8,
    "Trotskyism": 8,
    "Syndicalism": 8,
    "Luxemburgism": 8,
    "Strasserism": 10,
    "Maoism": 12,
    "Fascism": 12,
    "Marxism": 12,
    "Zionism": 12,
    "Centrism": 12,
    "Pacifism": 12,
    "Leninism": 12,
    "Populism": 12,
    "Futurism": 12,
    "Feminism": 12,
    "Humanism": 12,
    "Mutualism": 12,
    "Communism": 12,
    "Stalinism": 12,
    "Globalism": 12,
    "Socialism": 12,
    "Capitalism": 12,
    "Monarchism": 12,
    "Primitivism": 12,
    "Nationalism": 12,
    "Transhumanism": 12,
    "Traditionalism": 12,
    "Environmentalism": 12,
    "Accelerationism": 12
}

SUFFIXES = {
    " in One Country": 1,
    " with Chinese characteristics": 1,
    "": 28
}


@autoplugin
class Misc(Plugin):
    """
    Miscellaneous commands.
    """

    async def command_ideology(self, ctx: Context):
        """
        Creates an ideology just for you!
        """
        message = ''

        for d in (ADJECTIVES, PREFIXES, IDEOLOGIES, SUFFIXES):
            message += random.choices(list(d.keys()), list(d.values()))[0]

        await ctx.channel.messages.send(message)

    @ratelimit(limit=1, time=30)
    async def command_palette(self, ctx: Context, *, colours: List[int]):
        """
        Shows a palette plot.
        """
        pal_colours = rgbize(colours[:12])

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
