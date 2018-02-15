import datetime
import random
import re
from pprint import pprint
from typing import Tuple

import asks
import googlemaps
from asks.response_objects import Response
from curio.thread import async_thread
from curious import Embed
from curious.commands import Context, Plugin
from curious.commands.decorators import autoplugin

from jokusoramame import USER_AGENT
from jokusoramame.bot import Jokusoramame


def truncate(s: str) -> str:
    if len(s) <= 26:
        return s

    return s[:23] + "..."


bearing_map = {
    "S": "South",
    "N": "North",
    "E": "East",
    "W": "West",
    "NE": "Northeast",
    "NW": "Northwest",
    "SE": "Southeast",
    "SW": "Southwest"
}

BUS_REGEX = re.compile(r"[0-9]+[a-zA-Z]")


@autoplugin
class Location(Plugin):
    """
    Location utilities.
    """
    URL_PREFIX = "https://transportapi.com/v3/uk"

    def __init__(self, client: Jokusoramame):
        super().__init__(client)

        self.maps_client = googlemaps.Client(key=client.config['googlemapskey'])
        self.maps_client.requests_kwargs['headers']['User-Agent'] = USER_AGENT

    @async_thread
    def get_geocode(self, location: str) -> dict:
        """
        Gets the geocode of a location.
        """
        return self.maps_client.geocode(location)

    @async_thread
    def get_geodecode(self, latitude: int, longitude: int) -> dict:
        """
        Gets the geodecode of a lat/long pair.
        """
        return self.maps_client.reverse_geocode((latitude, longitude))

    async def get_lat_long(self, location: str) -> Tuple[float, float]:
        """
        Gets the latitude/longitude of a location.
        """
        geocode = await self.get_geocode(location)
        if len(geocode) == 0:
            raise ValueError("Invalid geocode")

        latlong = geocode[0]['geometry']['location']
        return latlong['lat'], latlong['lng']

    async def make_transport_api_request(self, route: str, params: dict) -> Response:
        """
        Makes a TransportAPI request.
        """
        params = {
            "app_id": self.client.config["transportapi"]["app_id"],
            "app_key": self.client.config["transportapi"]["app_key"],
            **params
        }
        headers = {
            "User-Agent": USER_AGENT
        }

        uri = self.URL_PREFIX + route
        result = await asks.get(uri=uri, params=params, headers=headers)
        return result

    async def get_atco(self, location: str) -> dict:
        """
        Gets the atco(s) of a location.
        """
        lat, long = await self.get_lat_long(location)
        route = "/bus/stops/near.json"
        result = await self.make_transport_api_request(
            route=route,
            params={"lat": lat, "lon": long, "rpp": 5},
        )
        return result.json()

    async def command_geocode(self, ctx: Context, *, location: str):
        """
        Geocodes a location, getting it's latitude/longitude.
        """
        lat, long = await self.get_lat_long(location)
        await ctx.channel.send(f"**Lat/long:** {lat} {long}")

    async def command_geodecode(self, ctx: Context, latitude: float, longitude: float):
        """
        Geodecodes a location, turning a lat/long pair into a location name.
        """
        geodecode = await self.get_geodecode(latitude, longitude)
        first = geodecode[0]['formatted_address']
        await ctx.channel.messages.send(f"**Geodecoded result:** {first}")

    async def command_bus(self, ctx: Context, *, stop: str):
        """
        Gets the bus schedule for a specified stop.

        Note that the stop might not be the one you specified; it is the closest one in the range of
        the area you specify.
        """
        if not BUS_REGEX.match(stop):
            async with ctx.channel.typing:
                atcos = await self.get_atco(stop)
                if len(atcos['stops']) == 0:
                    return await ctx.channel.messages.send(":x: Could not find this stop.")

            stop = atcos['stops'][0]
            atco = stop['atcocode']
        else:
            atco = stop

        return await self.command_bus_departures(ctx, atco=atco)

    async def command_bus_atco(self, ctx: Context, *, location: str):
        """
        Gets the ATCO code of a bus stop.
        """
        async with ctx.channel.typing:
            try:
                response = await self.get_atco(location)
            except ValueError as e:
                return await ctx.channel.messages.send(f":x: {''.join(e.args)}.")

        if len(response['stops']) == 0:
            return await ctx.channel.messages.send(":x: Could not find any stops here.")

        em = Embed()
        em.title = "Stop Search Results"
        for stop in response['stops']:
            em.add_field(name="Name", value=truncate(stop['stop_name']))
            em.add_field(name="ATCO", value=stop['atcocode'])
            em.add_field(name="Direction", value=bearing_map[stop['bearing']])

        em.set_footer(text="Powered by TransportAPI")
        em.timestamp = datetime.datetime.utcnow()
        em.colour = random.randint(0, 0xffffff)
        await ctx.channel.messages.send(embed=em)

    async def command_bus_departures(self, ctx: Context, *, atco: str):
        """
        Gets the live departures for a specified bus stop.
        """
        atco = atco.upper()

        async with ctx.channel.typing:
            url = f"/bus/stop/{atco}/live.json"
            result = await self.make_transport_api_request(url, params={
                "group": "route",
                "nextbuses": "yes"
            })
            js = result.json()
            if 'error' in js:
                return await ctx.channel.messages.send(f":x: API returned error: `{js['error']}`")

        embed = Embed()
        embed.title = f"Bus Departures for {js['name']}"
        embed.description = "This only lists the next bus arriving."

        for line, departure_list in js.get('departures', {}).items():
            departure = departure_list[0]
            embed.add_field(name="Route", value=str(line))
            direction = departure['direction']
            if len(direction) >= 27:
                direction = direction[:24] + "..."

            embed.add_field(name="Towards", value=direction)
            departure_time = departure['aimed_departure_time']
            if departure_time is None:
                departure_time = "EOTL"

            embed.add_field(name="Leaving at", value=departure_time)

        embed.set_footer(text="Powered by TransportAPI")
        embed.timestamp = datetime.datetime.utcnow()
        colour = random.randint(0, 0xffffff)
        embed.colour = colour

        await ctx.channel.messages.send(embed=embed)
