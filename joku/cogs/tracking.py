"""
NSA-tier presence tracking.
"""
import datetime
import time

import discord
from discord import Status
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context


class Tracking(Cog):
    async def on_message(self, message: discord.Message):
        author = message.author  # type: discord.Member

        # update their last message in redis
        await self.bot.redis.update_last_message(author)
        # and their last seen
        await self.bot.redis.update_last_seen(author)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # check to see if their after status is online and their before was not online
        if after.status is not Status.offline and before.status is not Status.online:
            await self.bot.redis.update_last_seen(after)

    @commands.command()
    async def tracking(self, ctx: Context, *, member: discord.Member=None):
        """
        Shows the last seen information for a member.
        """
        if member is None:
            member = ctx.message.author

        data = await self.bot.redis.get_presence_data(member)

        em = discord.Embed(title="National Security Agency")
        em.set_thumbnail(url=member.avatar_url)
        if data is None:
            em.description = "**No tracking data for this user was found.**"
        else:
            em.description = "**Tracking data for {}**".format(member.name)
            # float bugs
            if int(data["last_seen"]) == 0:
                if member.status == Status.online:
                    await ctx.bot.redis.update_last_seen(member)
                    last_seen = datetime.datetime.fromtimestamp(time.time()).isoformat()
                else:
                    last_seen = "Unknown"
            else:
                last_seen = datetime.datetime.fromtimestamp(data["last_seen"]).isoformat()

            if int(data["last_message"]) == 0:
                last_message = "Unknown"
            else:
                last_message = datetime.datetime.fromtimestamp(data["last_message"]).isoformat()

            em.add_field(name="Last seen", value=last_seen, inline=False)
            em.add_field(name="Last message", value=last_message, inline=False)

        await ctx.send(embed=em)


setup = Tracking.setup
