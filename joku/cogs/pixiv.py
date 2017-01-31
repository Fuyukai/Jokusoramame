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
from dateutil.parser import parse

from joku.bot import Context
from joku.cogs._common import Cog


class Pixiv(Cog):
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

    async def produce_embed(self, item: dict):
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

            embed = await self.produce_embed(item)
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

            embed = await self.produce_embed(item)

            try:
                await ctx.channel.send(embed=embed)
            except discord.HTTPException:
                await ctx.channel.send(":frowning: Discord didn't like our embed.")


def setup(bot):
    bot.add_cog(Pixiv(bot))
