"""
Analytical work.
"""
import entropy

import asks
import string
from asks.response_objects import Response
from curious import Member, event, EventContext, Message, Embed
from curious.commands import Plugin, command, Context


class Analytics(Plugin):
    @event("message_create")
    async def add_to_analytics(self, ctx: EventContext, message: Message):
        await ctx.bot.redis.add_message(message)

    @command()
    async def entropy(self, ctx: Context, *, message: str = None):
        """
        Gets the entropy of a sentence.
        """
        if message is None:
            # assume a file
            try:
                f = ctx.message.attachments[0]
            except IndexError:
                return await ctx.channel.send(":x: You must provide a message or attach a file.")

            async with ctx.channel.typing:
                r: Response = await asks.get(f.url)
            message = r.content
        else:
            message = message.encode('utf-8', errors='ignore')

        en = entropy.shannon_entropy(message)
        await ctx.channel.messages.send(f"Entropy: {en}")

    @command()
    async def analyse(self, ctx: Context):
        """
        Analyses various things about users or guilds.
        """
        return await ctx.channel.messages.send(":x: This command needs a valid subcommand.")

    @analyse.subcommand()
    async def member(self, ctx: Context, *, victim: Member = None):
        """
        Analyses a member.
        """
        if victim is None:
            victim = ctx.author

        async with ctx.channel.typing:
            messages = await ctx.bot.redis.get_messages(victim.user)
            if len(messages) == 0:
                return await ctx.channel.send(":x: No messages have been recorded for this member.")

            # do some processing
            total_entropy = 0
            total_length = 0

            # count capitals vs lowercase
            capitals = 0

            # track number of used messages
            used_messages = 0

            for message in messages:
                content = message["c"]
                if not content:
                    continue

                used_messages += 1

                total_entropy += entropy.shannon_entropy(content)
                total_length += len(content)
                capitals += sum(char in string.ascii_uppercase for char in content)

            # calculate averages
            avg_entropy = total_entropy / len(messages)
            avg_message_length = sum(len(m["c"]) for m in messages) / len(messages)

        em = Embed()
        em.title = "GHCQ Analysis Department"
        em.description = f"Analysis for {victim.user.username} used {used_messages} messages. " \
                         f"Skipped {len(messages) - used_messages} messages."
        em.colour = victim.colour
        em.set_thumbnail(url=victim.user.avatar_url)
        em.add_field(name="Avg. Entropy", value=format(avg_entropy, '.4f'))
        em.add_field(name="Avg. message length",
                     value=f"{format(avg_message_length, '.2f')} chars")
        em.add_field(name="Total message length", value=f"{total_length} chars")
        em.add_field(name="% capital letters",
                     value=format((capitals / total_length) * 100, '.2f'))

        await ctx.channel.messages.send(embed=em)
