"""
Cog for interacting with the Pixiv API.
"""
import random

import aiopixiv
import aiohttp
import asyncio
import discord

import threading
from discord.ext import commands
from io import BytesIO

from joku.bot import Context
from joku.cogs._common import Cog


class Pixiv(Cog):
    def __init__(self, bot):
        super().__init__(bot)

        # This is the authentciated API.
        self.pixiv = aiopixiv.PixivAPIv5()

        self.sess = aiohttp.ClientSession(loop=asyncio.get_event_loop())

    @commands.group(pass_context=True)
    async def pixiv(self, ctx: Context):
        """
        Commands for interacting with the Pixiv API.
        """

    @pixiv.command(pass_context=True)
    async def search(self, ctx: Context, *, tag: str):
        """
        Searches Pixiv using the specified tag.
        """
        await ctx.bot.type()
        if not self.pixiv.access_token:
            await self.pixiv.login(**ctx.bot.config.get("pixiv", {}))
        data = await self.pixiv.search_works(tag, per_page=100)

        if data.get("status") == "failure":
            await ctx.bot.say(":x: Failed to download from pixiv.")
            return

        # 'response' is the actual data key
        illusts = data["response"]

        if not illusts:
            await ctx.bot.say(":x: No results found.")
            return

        # Sort the illusts by score.
        illusts = sorted(illusts, key=lambda x: x["stats"]["score"], reverse=True)[:30]

        item = random.SystemRandom().choice(illusts)

        # Get some useful attributes out.
        obb = {
            "id": item["id"],
            "title": item["title"],
            "image": item["image_urls"]["large"],
            "username": item["user"]["name"],
            "url": "http://www.pixiv.net/member_illust.php?mode=medium&illust_id={}".format(item["id"]),
            "total_bookmarks": item["stats"]["favorited_count"]["public"],
            "views": item["stats"]["views_count"],
            "score": item["stats"]["score"]
        }

        image_data = await self.pixiv.download_pixiv_image(obb["image"])
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
                await ctx.bot.say(":x: An error occurred.")
                ctx.bot.logger.error(await r.text())
                return

            file_url = await r.text()

        # Create the embed object.
        title = "{title} - (ID: {id})".format(title=item["title"], id=item["id"])

        embed = discord.Embed(title=title)
        embed.url = "http://www.pixiv.net/member_illust.php?mode=medium&illust_id={}".format(item["id"])
        embed.set_author(name=item["user"]["name"],
                         url="http://www.pixiv.net/member.php?id={}".format(item["user"]["id"]))
        embed.set_image(url=file_url, height=360, width=480)

        await ctx.bot.say("\u200b", embed=embed)


def setup(bot):
    bot.add_cog(Pixiv(bot))
