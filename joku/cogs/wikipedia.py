"""
Wikipedia cog.
"""
from urllib.parse import urlencode, quote

import discord
import wikipedia
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context


def _wp_truncate(content: str) -> str:
    if len(content) <= 1000:
        return content

    return content[0:1000] + "..."


class Wikipedia(Cog):
    @commands.group(name="wikipedia", aliases=["wiki", "wp"], invoke_without_command=True)
    async def _wikipedia(self, ctx: Context, *, term: str):
        """
        Allows interfacing with Wikipedia.
        """
        await ctx.invoke(self.lookup, term=term)

    @_wikipedia.command(aliases=["summary"])
    async def lookup(self, ctx: Context, *, term: str):
        """
        Looks something up on Wikipedia.
        """

        def _get_wp_page():
            # always preload so that we dont accidentally block
            return wikipedia.page(title=term, preload=True)

        try:
            async with ctx.channel.typing():
                result = await self.bot.loop.run_in_executor(None, _get_wp_page)
        except wikipedia.DisambiguationError as e:
            em = discord.Embed(title="Disambiguation")
            em.description = "`{}` may refer to:" \
                             "\n\n{}".format(term,
                                             "\n".join(" - `{}`".format(x) for x in e.options))
            em.colour = discord.Colour.orange()
        except wikipedia.PageError as e:
            em = discord.Embed(title="Error")
            em.description = "Could not find any pages matching `{}`.".format(term)
            em.colour = discord.Colour.red()
        else:
            assert isinstance(result, wikipedia.WikipediaPage)
            em = discord.Embed(title=result.title)
            em.colour = discord.Colour.green()
            em.description = _wp_truncate(result.summary)
            em.url = result.url
            # only set thumbnail if the article has one
            try:
                em.set_thumbnail(url=result.images[0])
            except IndexError:
                pass

            # borrow this import thanks
            em.timestamp = wikipedia.datetime.utcnow()
            em.set_footer(text="Donate to Wikipedia today!",
                          icon_url="http://icons.iconarchive.com/icons/sykonist/"
                                   "popular-sites/256/Wikipedia-icon.png")

        await ctx.send(embed=em)

    @_wikipedia.command()
    async def search(self, ctx: Context, *, search_str: str):
        """
        Searches for something on wikipedia.
        """
        async with ctx.channel.typing():
            result = await self.bot.loop.run_in_executor(None, wikipedia.search, search_str)

        em = discord.Embed()
        if not result:
            em.colour = discord.Colour.red()
            fmt = "No results found."
        else:
            fmt = "Results for `{}`:\n\n".format(search_str)

            for result in result:
                built = "[{}](https://en.wikipedia.org/wiki/{})\n"\
                    .format(result, quote(result.replace(" ", "_")))
                fmt += built

        em.description = fmt
        await ctx.send(embed=em)

setup = Wikipedia.setup
