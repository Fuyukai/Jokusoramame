import asks
import datetime
import googlemaps
import random
import re
from asks.response_objects import Response
from curio.thread import async_thread
from curious import Embed
from curious.commands import Context, Plugin
from curious.commands.decorators import autoplugin
from curious.ext.paginator import ReactionsPaginator
from typing import Tuple

from jokusoramame import USER_AGENT
from jokusoramame.bot import Jokusoramame
from jokusoramame.utils import get_apikeys


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

        self.mapskey = get_apikeys("googlemaps")
        self.transportkey = get_apikeys("transport")

        self.maps_client = googlemaps.Client(key=self.mapskey.key)
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
            "app_id": self.transportkey.id_,
            "app_key": self.transportkey.key,
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
            params={"lat": lat, "lon": long},
        )
        return result.json()

    async def command_geocode(self, ctx: Context, *, location: str):
        """
        Geocodes a location, getting it's latitude/longitude.
        """
        lat, long = await self.get_lat_long(location)
        await ctx.channel.messages.send(f"**Lat/long:** {lat} {long}")

    async def command_geodecode(self, ctx: Context, latitude: float, longitude: float):
        """
        Geodecodes a location, turning a lat/long pair into a location name.
        """
        geodecode = await self.get_geodecode(latitude, longitude)
        first = geodecode[0]['formatted_address']
        await ctx.channel.messages.send(f"**Geodecoded result:** {first}")

    async def command_buses(self, ctx: Context, *, stop: str):
        """
        Gets the bus schedule for a specified UK bus stop.

        Note that the stop might not be the one you specified; it is the closest one in the range of
        the area you specify.
        """
        if not BUS_REGEX.match(stop):
            async with ctx.channel.typing:
                try:
                    atcos = await self.get_atco(stop)
                except ValueError:
                    return await ctx.channel.messages.send(":x: Could not find ATCO for this stop.")

                if len(atcos['stops']) == 0:
                    return await ctx.channel.messages.send(":x: Could not find this stop.")

            stop = atcos['stops'][0]
            atco = stop['atcocode']
        else:
            atco = stop

        return await self.command_buses_departures(ctx, atco=atco)

    async def command_buses_atco(self, ctx: Context, *, location: str):
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

        embeds = []
        for stop in response['stops']:
            em = Embed()
            em.title = "Stop Search Results"
            em.description = f"Full name: {stop['name']}"
            em.add_field(name="ATCO", value=stop['atcocode'], inline=False)

            bearing = stop['bearing']
            if bearing:
                bearing = bearing_map[bearing]
            else:
                bearing = "??"
            em.add_field(name="Direction", value=bearing)
            em.add_field(name="Indicator", value=stop['indicator'])
            em.add_field(name="Locality", value=stop['locality'])
            em.set_footer(text="Powered by TransportAPI")
            em.timestamp = datetime.datetime.utcnow()
            em.colour = random.randint(0, 0xffffff)
            embeds.append(em)

        paginator = ReactionsPaginator(embeds, ctx.channel, ctx.author)
        await paginator.paginate()

    async def command_buses_departures(self, ctx: Context, *, atco: str):
        """
        Gets the live departures for a specified bus stop.
        """
        atco = atco.upper()

        async with ctx.channel.typing:
            url = f"/bus/stop/{atco}/live.json"
            result = await self.make_transport_api_request(url, params={
                "group": "route",
                "nextbuses": "no"
            })
            js = result.json()
            if 'error' in js:
                return await ctx.channel.messages.send(f":x: API returned error: `{js['error']}`")

        embed = Embed()
        embed.title = f"Bus Departures for {js['name']}"
        embed.description = "This only lists the next bus arriving."

        if len(js['departures']) == 0:
            embed.description = "There are no buses departing this station currently."
        else:
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

    async def try_find_crs(self, station: str):
        """
        Tries to find a CRS code for the specified station.
        """
        lat, long = await self.get_lat_long(station)
        maxlat = lat - 1
        maxlong = long - 1
        minlat = lat + 1
        minlong = long + 1

        url = f"/train/stations/bbox.json"
        params = {
            "maxlat": maxlat,
            "maxlon": maxlong,
            "minlat": minlat,
            "minlon": minlong
        }
        result = await self.make_transport_api_request(url, params)
        result = result.json()

        station_results = result.get("stations", [])
        for r_station in result.get("stations", []):
            if r_station['name'].lower() == station.lower():
                return r_station['station_code']
        else:
            if len(station_results) > 0:
                return station_results[0]['station_code']

    async def command_trains(self, ctx: Context, *, station: str):
        """
        Shows information about the trains at a UK Train station.
        """
        if len(station) != 3:
            found_station = await self.try_find_crs(station)
            if found_station is None:
                # if all else fails, we can try a tiploc code
                station = f"tiploc:{station}"
            else:
                station = found_station

        return await self.command_trains_departures(ctx, station=station)

    async def command_trains_departures(self, ctx: Context, *, station: str):
        """
        Shows the train departures from the specified UK train station.
        """
        route = f"/train/station/{station}/live.json"
        params = {
            "station_detail": "origin,destination,calling_at,called_at",
            "type": "departure"
        }
        r = await self.make_transport_api_request(route, params)
        data = r.json()

        if 'error' in data:
            return await ctx.channel.messages.send(f":x: API gave error: {data['error']}")

        departures = data['departures']['all']
        if len(departures) == 0:
            em = Embed(title=f"Departures from {data['station_name']}")
            em.description = "There are currently no departures from this station."
            em.colour = random.randint(0, 0xffffff)
            return await ctx.channel.messages.send(embed=em)

        # used for pagination
        embeds = []

        for i, departure in enumerate(departures):
            dest = departure['destination_name']
            dest_station = departure['station_detail']['destination']

            em = Embed()
            em.title = f"Departures from {data['station_name']}"
            em.description = f"A {departure['operator_name']} service towards " \
                             f"{departure['destination_name']}.\n" \
                             f"This train is currently {departure['status'].lower()}"
            em.add_field(name="Origin", value=departure['origin_name'])
            em.add_field(name="Destination", value=dest)
            em.add_field(name="Expected arrival", value=departure['expected_arrival_time'])
            em.add_field(name="Expected departure", value=departure['expected_departure_time'])
            em.add_field(name="Platform at destination",
                         value=f"Platform {dest_station['platform']}")
            em.add_field(name="Arriving at destination",
                         value=f"{dest_station['aimed_arrival_time']}")
            em.set_footer(text=f"{i+1}/{len(departures)} trains")
            em.colour = random.randint(0, 0xffffff)
            embeds.append(em)

        paginator = ReactionsPaginator(embeds, ctx.channel, ctx.author)
        await paginator.paginate()
