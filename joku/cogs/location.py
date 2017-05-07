"""
Cog for interfacing with Google Maps and similar.
"""
import datetime
from io import BytesIO
from urllib.parse import urlencode

import aiohttp
import discord
import functools
import googlemaps
import pprint
from bingmaps.apiservices import TrafficIncidentsApi
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
    MQ_BASE = "https://www.mapquestapi.com"
    MQ_BETA = "https://beta.mapquestapi.com"

    MQ_MAPS = MQ_BETA + "/staticmap/v5/map"

    def __init__(self, bot: Jokusoramame):
        super().__init__(bot=bot)

        # Create the google maps client.
        self.maps = googlemaps.Client(key=self.bot.config["maps_api_key"])

    def make_mq_request(self, **kwargs):
        kwargs["key"] = self.bot.config["mapquest_api_key"]

        return kwargs

    @commands.command()
    async def map(self, ctx: Context, *, location: str):
        """
        Shows a map for the specified area.
        """
        # geocode the location
        async with ctx.channel.typing():
            geocode_result = await self.bot.loop.run_in_executor(None, self.maps.geocode, location)
            geocode_result = geocode_result[0]
            lat = geocode_result["geometry"]["location"]["lat"]
            long = geocode_result["geometry"]["location"]["lng"]

            req = self.make_mq_request(size="@2x", zoom=12,
                                       locations="{},{}".format(lat, long),
                                       traffic="flow|cons|inc")

            async with self.session.get(self.MQ_MAPS, params=req,
                                        headers={"Accept": "image/png"}) as r:
                assert isinstance(r, aiohttp.ClientResponse)
                if r.status != 200:
                    await ctx.send(":x: Something went wrong.")
                    raise RuntimeError(await r.text())

                data = BytesIO(await r.read())

        await ctx.send(file=data, filename="map.png")

    @commands.command()
    async def traffic(self, ctx: Context, *, location: str):
        """
        Shows traffic incidents at this location.
        """
        # this is broken!
        return
        # geocode it using google's API anyway, and then fetch from bing
        async with ctx.channel.typing():
            geocode_result = await self.bot.loop.run_in_executor(None, self.maps.geocode, location)
            geocode_result = geocode_result[0]
            lat = geocode_result["geometry"]["location"]["lat"]
            long = geocode_result["geometry"]["location"]["lng"]

            # calculate bounding box
            # south lat, west long, north lat, east long
            bounding_box = [lat - 0.1, long - 0.1, lat + 0.1, long + 0.1]

            result = TrafficIncidentsApi(self.make_bing_request(mapArea=bounding_box))

        pprint.pprint(result.traffic_incident())

    @commands.command()
    async def route(self, ctx: Context, from_: str, to: str):
        """
        Shows the route on a map from one place to another.
        """
        async with ctx.channel.typing():
            # do a double google maps geocode
            geocode_result = await self.bot.loop.run_in_executor(None, self.maps.geocode, from_)
            geocode_result = geocode_result[0]
            lat1 = geocode_result["geometry"]["location"]["lat"]
            long1 = geocode_result["geometry"]["location"]["lng"]

            geocode_result = await self.bot.loop.run_in_executor(None, self.maps.geocode, to)
            geocode_result = geocode_result[0]
            lat2 = geocode_result["geometry"]["location"]["lat"]
            long2 = geocode_result["geometry"]["location"]["lng"]

            req = self.make_mq_request(size="@2x",
                                       start="{},{}".format(lat1, long1),
                                       end="{},{}".format(lat2, long2))

            async with self.session.get(self.MQ_MAPS, params=req,
                                        headers={"Accept": "image/png"}) as r:
                assert isinstance(r, aiohttp.ClientResponse)
                if r.status != 200:
                    await ctx.send(":x: Something went wrong.")
                    raise RuntimeError(await r.text())

                data = BytesIO(await r.read())

        qs = urlencode({"saddr": from_, "daddr": to})
        final = "https://maps.google.com/?" + qs

        await ctx.send(final, file=data, filename="map.png")

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

    @commands.command(aliases=["ungeocode"])
    async def geodecode(self, ctx: Context, lat: float, long: float):
        """
        Decodes a lat/long pair into a place name.
        """
        async with ctx.channel.typing():
            geocode_result = await self.bot.\
                loop.run_in_executor(None, self.maps.reverse_geocode, (lat, long))

        if not geocode_result:
            await ctx.send(":x: That lat/long pair does not match any known location.")
            return

        wanted = geocode_result[0]

        em = discord.Embed(title="Geodecode")
        em.description = "The place here is **{}**.".format(wanted["formatted_address"])
        em.set_footer(text="Powered by Google Maps")

        em.add_field(name="Place types",
                     value=", ".join(x.replace("_", " ").capitalize() for x in wanted["types"]))
        em.add_field(name="Location type",
                     value=wanted["geometry"]["location_type"].replace("_", "").capitalize())

        em.colour = discord.Colour.green()

        em.timestamp = datetime.datetime.now()

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
            routes["start_address"], routes["end_address"], routes["duration"]["text"],
            routes["distance"]["text"]
        )

        qs = urlencode({"saddr": routes["start_address"], "daddr": routes["end_address"]})
        final = "https://maps.google.com/?" + qs

        if len(routes["steps"]) > 15:
            # build the url
            em.description += "\n\n**This has more than 15 steps.** " \
                              "To see the full route, go to {}.".format(final)

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
