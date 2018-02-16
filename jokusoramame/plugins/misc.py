from io import BytesIO
from typing import Awaitable, List

import matplotlib.pyplot as plt
import seaborn as sns
from curio.thread import async_thread
from curious.commands import Context, Plugin
from curious.commands.decorators import autoplugin, ratelimit


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

        if ctx.bot._plot_lock.locked():
            await ctx.channel.messages.send("Waiting for plot lock...")

        async with ctx.channel.typing:
            buf = await plot_palette()

        await ctx.channel.messages.upload(fp=buf.read(), filename="plot.png")