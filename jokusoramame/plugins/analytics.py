"""
Analytical work.
"""
import entropy
import string

import asks
from asks.response_objects import Response
from curious import Embed, EventContext, Member, Message, event
from curious.commands import Context, Plugin, command


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
    async def toggle(self, ctx: Context, *, guild_id: int):
        """
        Toggles analytics for the specified guild ID.
        """
        if ctx.author.id != 214796473689178133:
            return await ctx.channel.messages.send(":x: Analytics are expensive, so only the owner"
                                                   "can enable them.")

        guild = ctx.bot.guilds.get(guild_id)
        if guild is None:
            return await ctx.channel.send(":x: This guild does not exist.")

        enabled = await ctx.bot.redis.toggle_analytics(guild)
        await ctx.channel.messages.send(f":heavy_check_mark: Analytics status: {enabled}")

    async def analyse_member(self, member: Member) -> dict:
        """
        Analyses a member's messages, returning a dictionary of statistics.
        """
        messages = await self.client.redis.get_messages(member.user)
        if len(messages) == 0:
            return {}

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

        return {
            "message_count": used_messages,
            "message_total": len(messages),
            "total_entropy": total_entropy,
            "total_length": total_length,
            "average_entropy": avg_entropy,
            "average_length": avg_message_length,
            "capitals": capitals
        }

    @analyse.subcommand()
    async def member(self, ctx: Context, *, victim: Member = None):
        """
        Analyses a member.
        """
        if victim is None:
            victim = ctx.author

        async with ctx.channel.typing:
            processed = await self.analyse_member(victim)
            if not processed:
                return await ctx.channel.messages.send(":x: There are no analytics available for "
                                                       "this user.")

        messages = processed['message_total']
        used_messages = processed['message_count']
        avg_entropy = processed['average_entropy']
        avg_length = processed['average_length']
        total_length = processed['total_length']
        capitals = processed['capitals']
        em = Embed()
        em.title = "GHCQ Analysis Department"
        em.description = f"Analysis for {victim.user.username} used {used_messages} " \
                         f"messages. Skipped {messages - used_messages} messages."
        em.colour = victim.colour
        em.set_thumbnail(url=str(victim.user.avatar_url))
        em.add_field(name="Avg. Entropy", value=format(avg_entropy, '.4f'))
        em.add_field(name="Avg. message length",
                     value=f"{format(avg_length, '.2f')} chars")
        em.add_field(name="Total message length", value=f"{total_length} chars")
        em.add_field(name="% capital letters",
                     value=format((capitals / total_length) * 100, '.2f'))

        await ctx.channel.messages.send(embed=em)
