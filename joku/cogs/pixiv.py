"""
Cog for interacting with the Pixiv API.
"""
import random
import shutil

import requests
from discord.ext import commands
from io import BytesIO
from pixivpy3 import AppPixivAPI
from asyncio_extras import threadpool
from pixivpy3 import PixivAPI
from pixivpy3 import PixivError

from joku.bot import Context


class EncodingAwarePixivAPI(PixivAPI):
    """
    A custom encoding-aware Pixiv API.
    """

    def requests_call(self, method, url, headers=None, params=None, data=None, stream=False):
        """ requests http/https call for Pixiv API """
        if headers is None:
            headers = {}
        try:
            if method == 'GET':
                r = requests.get(url, params=params, headers=headers, stream=stream, **self.requests_kwargs)
            elif method == 'POST':
                r = requests.post(url, params=params, data=data, headers=headers, stream=stream,
                                  **self.requests_kwargs)
            elif method == 'DELETE':
                r = requests.delete(url, params=params, data=data, headers=headers, stream=stream,
                                    **self.requests_kwargs)
            else:
                raise PixivError('Unknown method: %s' % method)
            r.encoding = "utf-8"
            return r
        except Exception as e:
            raise PixivError('requests %s %s error: %s' % (method, url, e)) from e


class Pixiv(object):
    def __init__(self, bot):
        self.bot = bot

        # This is the authentciated API.
        self._pixiv_api = EncodingAwarePixivAPI()

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
        async with threadpool():
            if not self._pixiv_api.access_token:
                self._pixiv_api.auth(**ctx.bot.config.get("pixiv", {}))
            data = self._pixiv_api.search_works(tag, per_page=100)

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

        async with threadpool():
            # Download the image.
            r = self._pixiv_api.requests_call('GET', obb["image"],
                                              headers={'Referer': "https://app-api.pixiv.net/"},
                                              stream=True)

            # Copy it into BytesIO, which wiull be uploaded to Discord.
            fobj = BytesIO()
            shutil.copyfileobj(r.raw, fobj)
            # Seek back, so that it acutally uploads a file.
            fobj.seek(0)

        await ctx.bot.say("`{title}`, by **{username}** (Illustration ID `{id}`):\n"
                          "\n**{score}** score, **{total_bookmarks}** bookmarks, **{views}** views"
                          "\n<{url}>".format(**obb))

        await ctx.bot.type()

        await ctx.bot.upload(fobj, filename=obb["image"].split("/")[-1])


def setup(bot):
    bot.add_cog(Pixiv(bot))
