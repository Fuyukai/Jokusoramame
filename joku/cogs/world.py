import aiohttp
import datetime
import arrow
import discord
import pytz
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Jokusoramame, Context


class NASAException(Exception):
    pass


class World(Cog):
    """
    Cog for interacting with data about the real world.
    """

    async def make_nasa_request(self, url: str, params: dict = None) -> dict:
        """
        Makes a request to the NASA API.
        """
        key = self.bot.config["nasa_api_key"]
        if params is None:
            params = {}
        params = {"api_key": key, **params}

        async with self.session.get(url, params=params) as r:
            if r.status != 200:
                text = await r.text()
                raise NASAException(text)

            return await r.json()

    @commands.command()
    async def earthquakes(self, ctx: Context):
        """
        Shows recent earthquakes.
        """
        async with self.session.get("http://earthquake-report.com/feeds/recent-eq?json") as r:
            data = await r.json()

        data = data[0]

        em = discord.Embed()
        em.title = "Earthquakes"
        em.description = data["title"].split("-")[0]

        # Hack to make the embed 2 columns wide
        em.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/5/59/Empty.png")

        em.add_field(name="Location", value=data["location"].strip(), inline=False)
        em.add_field(name="Magnitude", value="{:.2f}".format(float(data["magnitude"])))
        em.add_field(name="Depth", value="{} km".format(data["depth"]))

        em.add_field(name="Latitude", value=data["latitude"])
        em.add_field(name="Longitude", value=data["longitude"])

        em.url = data["link"]
        ts = arrow.get(data["date_time"]).datetime.astimezone(pytz.UTC)
        em.timestamp = ts
        em.set_footer(text="Powered by http://earthquake-report.com")
        await ctx.send(embed=em)

    @commands.group(name="nasa")
    async def nasa(self, ctx: Context):
        """
        Allows you to query NASA data.
        """

    @nasa.command()
    async def apod(self, ctx: Context):
        """
        Displays the Astronomical Picture Of the Day.
        """
        url = "https://api.nasa.gov/planetary/apod"

        async with ctx.channel.typing():
            data = await self.make_nasa_request(url)

            em = discord.Embed(title=data["title"])
            em.description = data["explanation"]
            em.url = data["url"]
            em.set_image(url=data["hdurl"])

            if 'copyright' in data:
                em.set_footer(text="Powered by the NASA API "
                                   "| Copyright (C) {}".format(data["copyright"]),
                              icon_url="https://images.nasa.gov/images/"
                                       "nasa_logo-large.ee501ef4.png")
            else:
                em.set_footer(text="Powered by the NASA API",
                              icon_url="https://images.nasa.gov/images/"
                                       "nasa_logo-large.ee501ef4.png")

            await ctx.send(embed=em)

    @nasa.command()
    async def imagery(self, ctx: Context, lat: float, long: float, date: str=None):
        """
        Displays a satellite image at the specified latitude and longitude.
        
        To find your lat/long, you can use `j!geocode <place>`.
        
        An optional date can be provided which will attempt to show data from that date. This date 
        must be in  YY-MM-DD format.
        """
        url = "https://api.nasa.gov/planetary/earth/imagery"
        params = {"lat": str(lat), "lon": str(long), "cloud_score": "True"}

        if date is not None:
            params["date"] = date

        async with ctx.channel.typing():
            data = await self.make_nasa_request(url, params)

            if 'error' not in data:
                em = discord.Embed(title=data["id"])
                em.set_image(url=data["url"])
                em.url = data["url"]
                # em.timestamp = arrow.get(data["date"]).datetime
                em.add_field(name="Cloud coverage (est)",
                             value="{}%".format(round(data["cloud_score"] * 100, 2)))
                em.add_field(name="Picture date", value=data["date"])
                em.colour = discord.Colour.green()

            else:
                em = discord.Embed(title="Error fetching image data")
                em.description = data["error"]
                em.description += "\n\n**Try a different date.**"
                em.colour = discord.Colour.red()

            em.set_footer(text="All data provided by the NASA API (https://api.nasa.gov).",
                          icon_url="https://images.nasa.gov/images/nasa_logo-large.ee501ef4.png")

        await ctx.send(embed=em)

    @nasa.command()
    async def neo(self, ctx: Context):
        """
        Shows a random Near Earth Object that is passing within the next 7 days.
        
        http://cneos.jpl.nasa.gov/
        """
        url = "https://api.nasa.gov/neo/rest/v1/feed"
        start = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        params = {"start_date": start}

        async with ctx.channel.typing():
            data = await self.make_nasa_request(url, params)
            # nasa API is ok if a bit weird
            # pick a random day
            date = self.rng.choice(list(data["near_earth_objects"].keys()))
            dt = arrow.get(date).datetime.astimezone(pytz.UTC)

            # get the object
            neo_object = self.rng.choice(data["near_earth_objects"][date])

            em = discord.Embed(title=neo_object["name"], url=neo_object["nasa_jpl_url"])

            # add useful fields
            em.add_field(name="Potentially hazardous?",
                         value=neo_object["is_potentially_hazardous_asteroid"])
            em.add_field(name="Pass date", value=date)
            em.add_field(name="Absolute magnitude", value=neo_object["absolute_magnitude_h"])

            # extract the estimated diameter
            diameters = neo_object["estimated_diameter"]["meters"]
            avg = (diameters["estimated_diameter_min"] + diameters["estimated_diameter_max"]) // 2
            em.add_field(name="Estimated diameter", value="{} m".format(avg))

            # extract the close approach data
            cad = neo_object["close_approach_data"][0]
            rel_vel = round(float(cad["relative_velocity"]["kilometers_per_second"]), 2)
            miss_distance = round(float(cad["miss_distance"]["astronomical"]), 2)

            em.add_field(name="Relative velocity", value="{} km/s".format(rel_vel))
            em.add_field(name="Closest approach", value="{} AU".format(miss_distance))
            em.set_footer(text="All data provided by the NASA API (https://api.nasa.gov).",
                          icon_url="https://images.nasa.gov/images/nasa_logo-large.ee501ef4.png")

            em.colour = discord.Colour.light_grey()

        await ctx.send(embed=em)


setup = World.setup
