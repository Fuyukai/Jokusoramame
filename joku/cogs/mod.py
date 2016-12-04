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


class Moderation(Cog):
    """
    Non-generic moderation cog.
    """

    @commands.command(pass_context=True)
    async def islandbot(self, ctx: Context):
        """
        Who will be voted off of the island?
        """
        message = ctx.message  # type: discord.Message
        channel = message.channel

        # Begin the raffle!
        timeout = random.randrange(30, 60)

        await ctx.bot.say(":warning: :warning: :warning: Raffle ends in **{}** seconds!".format(timeout))

        # messages to collect
        messages = []

        async def _inner():
            # inner closure point - this is killed by asyncio.wait()
            while True:
                next_message = await ctx.bot.wait_for_message(channel=channel)
                if next_message.author == message.server.me:
                    continue
                # Do some checks on the user to make sure we can kick them.
                if next_message.author.server_permissions.administrator:
                    continue

                if next_message.author.top_role >= message.server.me.top_role:
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

        fmt = ":island: These people are up for vote:\n\n{}\n\nMention to vote.".format(
            "\n".join(m.mention for m in chosen)
        )
        await ctx.bot.say(fmt)

        votes = []
        voted = []

        async def _inner2():
            while True:
                next_message = await ctx.bot.wait_for_message(channel=channel)
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
                    await ctx.bot.send_message(channel, "I am not a tool for assisted suicide")
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
        winner = counted.most_common()[0]

        await ctx.bot.say(":medal: The winner is {}, with `{}` votes!".format(winner[0].mention, winner[1]))
        try:
            await ctx.bot.send_message(winner[0], "You have been voted off the island.")
        except discord.HTTPException:
            pass

        try:
            await ctx.bot.kick(winner[0])
        except discord.HTTPException:
            await ctx.bot.send_message(channel, "The island is rigged")

setup = Moderation.setup
