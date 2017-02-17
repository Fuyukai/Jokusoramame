"""
Cog for interfacing with Google Maps and similar.
"""
import datetime
from urllib.parse import urlencode

import discord
import functools
import googlemaps
import pprint
from discord.ext import commands
from discord.ext.commands import BucketType

from joku.cogs._common import Cog
from joku.core.bot import Jokusoramame, Context


def _sanitize_html_instructions(s: str) -> str:
    """
    Sanitizes the google maps HTML instructions.
    """
    # remove <b> and </b> tags
    s = s.replace("<b>", "**").replace("</b>", "**")

    # remove divs
    s = s.replace('<div style="font-size:0.9em">', '\n').replace("</div>", "")

    return s


class Location(Cog):
    def __init__(self, bot: Jokusoramame):
        super().__init__(bot=bot)

        # Create the google maps client.
        self.maps = googlemaps.Client(key=self.bot.config["maps_api_key"])

    @commands.command()
    async def geocode(self, ctx: Context, *, location: str):
        """
        Geocodes a location into a latitude / longitude pair.
        """
        async with ctx.channel.typing():
            geocode_result = await self.bot.loop.run_in_executor(None, self.maps.geocode, location)
        result = geocode_result[0]  # type: dict

        em = discord.Embed(title="Geocode Results")
        em.description = "Geocode results for {}".format(location)

        em.add_field(name="Latitude", value=result["geometry"]["location"]["lat"])
        em.add_field(name="Longitude", value=result["geometry"]["location"]["lng"])

        em.colour = discord.Colour.green()
        em.set_footer(text="Powered by Google Maps")
        em.timestamp = datetime.datetime.utcnow()

        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(rate=1, per=5, type=BucketType.channel)
    async def directions(self, ctx: Context, from_: str, to: str):
        """
        Shows you directions from the location `from_`, to the destination `to`.
        
        This will only show a maximum of 15 directions.
        """
        async with ctx.channel.typing():
            route = await self.bot.loop.run_in_executor(None, functools.partial(
                self.maps.directions, origin=from_, destination=to
            ))

        if not route:
            await ctx.send(":no_entry_sign: Could not resolve directions between these two places.")
            return

        routes = route[0]["legs"][0]
        em = discord.Embed(title="Directions Results")
        em.description = "From **{}** to **{}** will take you **{}** over **{}**.".format(
            routes["start_address"], routes["end_address"], routes["duration"]["text"], routes["distance"]["text"]
        )

        qs = urlencode({"saddr": routes["start_address"], "daddr": routes["end_address"]})
        final = "https://maps.google.com/?" + qs

        if len(routes["steps"]) > 15:
            # build the url
            em.description += "\n\n**This has more than 15 steps.** To see the full route, go to {}.".format(final)

        em.url = final
        for n, step in enumerate(routes["steps"]):
            if n == 15:
                # no more than 15 steps
                break

            # get the route string
            title = "**{}** ({}, {})".format(step["travel_mode"].capitalize(),
                                             step["distance"]["text"], step["duration"]["text"])
            value = _sanitize_html_instructions(step["html_instructions"])
            em.add_field(name=title, value=value, inline=False)

        await ctx.send(embed=em)


setup = Location.setup
