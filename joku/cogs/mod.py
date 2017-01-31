"""
Non-generic moderation cog.
"""
import asyncio
import random
import collections

import discord
from discord.ext import commands

from joku.bot import Context
from joku.cogs._common import Cog
from joku import checks


class Moderation(Cog):
    """
    Non-generic moderation cog.
    """

    async def on_member_remove(self, member: discord.Member):
        # Rolestate
        await self.bot.rethinkdb.save_rolestate(member)

    async def on_member_join(self, member: discord.Member):
        # Rolestate
        setting = await self.bot.rethinkdb.get_setting(member.guild, "rolestate", {})
        if setting.get("status") == 1:
            roles, nick = await self.bot.rethinkdb.get_rolestate_for_member(member)

            await member.edit(roles=roles)
            if nick:
                await member.edit(nick=nick)

    async def on_message(self, message: discord.Message):
        # Anti mention spam

        # Use a set here as we only want to ban unique mentions
        mentions = len(set(message.mentions))
        if mentions < 3:
            # dont bother loading from DB
            return

        if message.guild is None:
            return

        if message.author.top_role >= message.guild.me.top_role or message.author == message.guild.owner:
            # can't ban anyway
            return

        c = await self.bot.rethinkdb.get_setting(message.guild, "mention_spam", {
            "value": False,
            "threshold": 5
        })
        if c["value"] is True:
            if mentions == c["threshold"]:
                guild = message.guild  # type: discord.Guild
                await guild.ban(message.author)
                await message.channel.send("Member **{}** was automatically banned for going over the mention spam "
                                           "limit.".format(message.author))

    # anti mention spam
    @commands.group(pass_context=True, invoke_without_command=True)
    @checks.has_permissions(ban_members=True)
    async def antimention(self, ctx: Context, *, status: str = None):
        """
        Toggles the antimention status in this server.
        """
        previous = await ctx.bot.rethinkdb.get_setting(ctx.guild, "mention_spam", {
            "value": False,
            "threshold": 5
        })
        if status is None or status not in ["on", "off"]:
            current_status = previous.get("value", False)
            if current_status:
                await ctx.send("Anti-mention spam is currently **on**.")
            else:
                await ctx.send("Anti-mention spam is currently **off**.")

            return

        if status == "on":
            await ctx.bot.rethinkdb.set_setting(ctx.guild, "mention_spam",
                                                **{
                                                    "value": True,
                                                    "threshold": previous["threshold"]
                                                })
            await ctx.send(":heavy_check_mark: Enabled anti-mention spam.")
        elif status == "off":
            await ctx.bot.rethinkdb.set_setting(ctx.guild, "mention_spam",
                                                **{
                                                    "value": False,
                                                    "threshold": previous["threshold"]
                                                })
            await ctx.send(":heavy_check_mark: Disabled anti-mention spam.")

    @antimention.command()
    async def threshold(self, ctx: Context, threshold: int):
        """
        Changes the threshold for anti-mention spam to ban at.
        """
        if threshold < 3:
            await ctx.send(":x: Cannot set a threshold lower than 3.")
            return

        previous = await ctx.bot.rethinkdb.get_setting(ctx.guild, "mention_spam", {
            "value": False,
            "threshold": 5
        })
        await ctx.bot.rethinkdb.set_setting(ctx.guild, "mention_spam", value=previous["value"], threshold=threshold)
        await ctx.send(":heavy_check_mark: Set anti-mention spam threshold to {}.".format(threshold))

    @commands.command(pass_context=True)
    @checks.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def xban(self, ctx: Context, user_id: str):
        """
        Cross-bans a user.
        """
        if user_id in [m.id for m in ctx.message.server.members]:
            await ctx.channel.send(":x: This command is used for banning members not in the server.")
            return

        try:
            user = await ctx.bot.get_user_info(user_id)
            await ctx.bot.http.ban(user_id, ctx.message.server.id, 0)
        except discord.Forbidden:
            await ctx.channel.send(":x: 403 FORBIDDEN")
        except discord.NotFound:
            await ctx.channel.send(":x: User not found.")
        else:
            await ctx.channel.send(":heavy_check_mark: Banned user {}.".format(user.name))

    @commands.command(pass_context=True)
    @commands.cooldown(rate=1, per=5 * 60, type=commands.BucketType.guild)
    @checks.has_permissions(kick_members=True)
    async def islandbot(self, ctx: Context):
        """
        Who will be voted off of the island?
        """
        message = ctx.message  # type: discord.Message
        channel = message.channel

        # Begin the raffle!
        timeout = random.randrange(30, 60)

        await ctx.channel.send(":warning: :warning: :warning: Raffle ends in **{}** seconds!".format(timeout))

        # messages to collect
        messages = []

        async def _inner():
            # inner closure point - this is killed by asyncio.wait()
            while True:
                next_message = await ctx.bot.wait_for("message", check=lambda m: m.channel == channel)
                if next_message.author == message.guild.me:
                    continue
                # Do some checks on the user to make sure we can kick them.
                if next_message.author.guild_permissions.administrator:
                    continue

                if next_message.author.top_role >= message.guild.me.top_role:
                    continue

                messages.append(next_message)

        try:
            # wait for the waiter, but discard it when we're done
            await asyncio.wait_for(_inner(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        # gather all the users in the messages
        authors = list({m.author for m in messages})
        # Choose some random people from the authors.
        chosen = []
        for x in range(0, min(len(authors), 5)):
            r = random.choice(authors)
            chosen.append(r)
            authors.remove(r)

        if not chosen:
            await ctx.channel.send(":x: Nobody entered the raffle")
            return

        fmt = ":island: These people are up for vote:\n\n{}\n\nMention to vote.".format(
            "\n".join(m.mention for m in chosen)
        )
        await ctx.channel.send(fmt)

        votes = []
        voted = []

        async def _inner2():
            while True:
                next_message = await ctx.bot.wait_for("message", check=lambda m: m.channel == channel)
                # Ignore bots.
                if next_message.author.bot:
                    continue

                # No double voting.
                if next_message.author in voted:
                    continue

                # They didn't mention anyone.
                if not next_message.mentions:
                    continue

                # Check the first mention.
                m = next_message.mentions[0]

                # You can't vote for somebody not in the raffle!
                if m not in chosen:
                    continue

                if m == next_message.author:
                    await ctx.send("I am not a tool for assisted suicide")
                    continue

                # Add them to the votes, and add the author to the voted count.
                votes.append(m)
                voted.append(next_message.author)

        try:
            # wait for the waiter, but discard it when we're done
            await asyncio.wait_for(_inner2(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        # Count the votes.
        counted = collections.Counter(votes)
        try:
            winner = counted.most_common()[0]
        except IndexError:
            await ctx.channel.send(":bomb: Nobody voted")
            return

        await ctx.channel.send(":medal: The winner is {}, with `{}` votes!".format(winner[0].mention, winner[1]))
        try:
            await winner[0].send("You have been voted off the island.")
        except discord.HTTPException:
            pass

        try:
            await ctx.guild.kick(winner[0])
        except discord.HTTPException:
            await ctx.send(channel, "The island is rigged")

    @commands.command(pass_context=True)
    @checks.has_permissions(manage_nicknames=True)
    async def massnick(self, ctx: Context, prefix: str = "", suffix: str = ""):
        """
        Mass-nicknames an entire server.
        """
        coros = []

        for member in ctx.message.guild.members:
            coros.append(member.edit(nick=prefix + member.name + suffix))

        fut = asyncio.gather(*coros, return_exceptions=True, loop=ctx.bot.loop)

        async with ctx.channel.typing():
            await fut

        count = sum(1 for i in fut.result() if not isinstance(i, Exception))
        forbidden = sum(1 for i in fut.result() if isinstance(i, discord.Forbidden))
        httperror = sum(1 for i in fut.result() if isinstance(i, discord.HTTPException)) - forbidden
        failed = ctx.message.server.member_count - count

        await ctx.channel.send(
            ":heavy_check_mark: Updated `{}` nicknames - failed to change `{}` nicknames. "
            "(`{}` forbidden, `{}` too long/other)".format(count, failed, forbidden, httperror)
        )


setup = Moderation.setup
