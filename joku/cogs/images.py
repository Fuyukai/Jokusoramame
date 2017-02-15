"""
Cog for interacting with various image APIs.
"""
import asyncio
import random
from io import BytesIO

import aiohttp
import aiopixiv
import arrow
import discord
import pytz
from dateutil.parser import parse
from discord.ext import commands

from joku import VERSION
from joku.cogs._common import Cog
from joku.core.bot import Context


class Images(Cog):
    UNSPLASH_BASE = "https://api.unsplash.com"
    UNSPLASH_RANDOM_PHOTO = UNSPLASH_BASE + "/photos/random"
    UNSPLASH_SEARCH = UNSPLASH_BASE + "/search/photos"

    def __init__(self, bot):
        super().__init__(bot)

        # This is the authentciated API.
        self.pixiv = aiopixiv.PixivAPIv5()

        self.sess = aiohttp.ClientSession(loop=asyncio.get_event_loop())

    @commands.group(pass_context=True, invoke_without_command=True, name="pixiv")
    async def _pixiv(self, ctx: Context):
        """
        Commands for interacting with the Pixiv API.
        """

    async def pixiv_produce_embed(self, item: dict):
        """
        Produces an embed from a Pixiv illustration object.
        """
        if item.get("work"):
            item = item["work"]
        image_data = await self.pixiv.download_pixiv_image(item["image_urls"]["large"])
        # Upload to catbox.moe, because pixiv sucks
        fobj = BytesIO(image_data)

        data = aiohttp.FormData()
        data.add_field("reqtype", "fileupload")
        data.add_field(
            "fileToUpload",
            fobj,
            filename="upload.png"
        )

        async with self.sess.post("https://catbox.moe/user/api.php", data=data) as r:
            if r.status != 200:
                return
            file_url = await r.text()

        # Create the embed object.
        title = "{title} - (ID: {id})".format(title=item["title"], id=item["id"])

        embed = discord.Embed(title=title, description=item["caption"])
        embed.url = "http://www.pixiv.net/member_illust.php?mode=medium&illust_id={}".format(item["id"])
        embed.set_author(name=item["user"]["name"],
                         url="http://www.pixiv.net/member.php?id={}".format(item["user"]["id"]))
        embed.set_image(url=file_url)
        # Parse the timestamp from the data.
        timestamp = parse(item["created_time"])
        embed.timestamp = timestamp

        footer_text = "Views: {} | Score: {}".format(item["stats"]["views_count"], item["stats"]["score"])

        embed.set_footer(text=footer_text)

        return embed

    @_pixiv.command(pass_context=True)
    async def daily(self, ctx: Context):
        """
        Gets a random item from the top 100 daily illustrations.
        """
        async with ctx.channel.typing():
            if not self.pixiv.access_token:
                await self.pixiv.login(**ctx.bot.config.get("pixiv", {}))

            data = await self.pixiv.get_rankings(per_page=100)

            illusts = data["response"]

            item = random.SystemRandom().choice(illusts)

            embed = await self.pixiv_produce_embed(item)
            if embed:
                try:
                    await ctx.channel.send(embed=embed)
                except discord.HTTPException:
                    await ctx.channel.send(":frowning: Discord didn't like our embed.")

    @_pixiv.command(pass_context=True)
    async def search(self, ctx: Context, *, tag: str):
        """
        Searches Pixiv using the specified tag.
        """
        async with ctx.channel.typing():
            if not self.pixiv.access_token:
                await self.pixiv.login(**ctx.bot.config.get("pixiv", {}))
            data = await self.pixiv.search_works(tag, per_page=100)

            if data.get("status") == "failure":
                await ctx.channel.send(":x: Failed to download from pixiv.")
                return

            # 'response' is the actual data key
            illusts = data["response"]

            if not illusts:
                await ctx.channel.send(":x: No results found.")
                return

            # Sort the illusts by score.
            illusts = sorted(illusts, key=lambda x: x["stats"]["score"], reverse=True)[:30]

            item = random.SystemRandom().choice(illusts)

            embed = await self.pixiv_produce_embed(item)

            try:
                await ctx.channel.send(embed=embed)
            except discord.HTTPException:
                await ctx.channel.send(":frowning: Discord didn't like our embed.")

    async def make_unsplash_request(self, url: str, *, params: dict = None):
        """
        Makes a request to Unsplash using the right headers.
        """
        headers = {
            "User-Agent": "DiscordBot Jokusoramame/{}".format(VERSION),
            "Authorization": "Client-ID {}".format(self.bot.config["unsplash_client_id"]),
            "Accept-Version": "v1",
            "X-You-Are-Awesome": "true"
        }

        async with self.sess.get(url, headers=headers, params=params) as r:
            assert isinstance(r, aiohttp.ClientResponse)
            if r.status == 401:
                raise RuntimeError("Token invalid for Unsplash")

            return await r.json()

    def make_unsplash_embed(self, req: dict) -> discord.Embed:
        em = discord.Embed(title=req["id"])
        # credit the author
        description = "Photo by [{name}]({url}) / [Unsplash](https://unsplash.com/)."
        em.description = description.format(name=req["user"]["name"], url=req["user"]["links"]["html"])
        # add the image (obviously)
        em.set_image(url=req["urls"]["full"])
        em.url = req["links"]["html"]
        em.colour = discord.Colour(int(req["color"][1:], 16))
        # add the author again anyway
        em.set_author(name=req["user"]["name"], url=req["user"]["links"]["html"])

        # there has got to be a better way
        class _ts:
            _ = arrow.get(req["created_at"]).datetime.astimezone(pytz.UTC)

            def isoformat(self):
                return self._.strftime("%Y-%m-%dT%H:%M:%S.%f")

        em._timestamp = _ts()

        return em

    @commands.group(pass_context=True, invoke_without_command=True, name="unsplash")
    async def _unsplash(self, ctx: Context):
        """
        Displays images from unsplash. 
        """

    @_unsplash.command(pass_context=True)
    async def random(self, ctx: Context):
        """
        Shows a random image from Unsplash.
        """
        req = await self.make_unsplash_request(self.UNSPLASH_RANDOM_PHOTO)

        em = self.make_unsplash_embed(req)
        await ctx.send(embed=em)

    @_unsplash.command(pass_context=True)
    async def search(self, ctx: Context, *, search_text: str):
        """
        Searches Unsplash for an image.
        """
        async with ctx.channel.typing():
            results = await self.make_unsplash_request(self.UNSPLASH_SEARCH, params={
                "query": search_text,
                "per_page": 50
            })
        req = random.choice(results["results"])

        em = self.make_unsplash_embed(req)
        await ctx.send(embed=em)


def setup(bot):
    bot.add_cog(Images(bot))
