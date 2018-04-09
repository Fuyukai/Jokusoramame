"""
Autoprune functionality.
"""
import collections
import datetime
import random

import numpy as np
from curious import Embed, Guild
from curious.commands import Context, Plugin, command, condition
from dataclasses import dataclass

from jokusoramame.redis import RedisInterface


@dataclass
class ActivityReport:
    active: bool
    algo_result: float
    post_count: int
    last_message: datetime.datetime
    days_inactive: int = 0


class Autoprune(Plugin):
    """
    Handles better automatic pruning.
    """

    @staticmethod
    def prune_condition(ctx: Context):
        # backdoor tm
        # TODO: integrate full permissions backdoor
        return ctx.author.guild_permissions.kick_membmers or ctx.author.id == 214796473689178133

    @command()
    async def activity(self, ctx: Context):
        """
        Shows activity statistics for this server. Analytics must be enabled.
        """
        skipped = 0
        analysed = 0
        time_bins = collections.Counter()
        message_count = 0
        members = ctx.guild.members.values()

        async with ctx.channel.typing:
            for member in members:
                messages = await ctx.bot.redis.get_messages(member.user)
                # skip any flagged members
                if messages == ctx.bot.redis.FLAGGED:
                    skipped += 1
                    continue

                if len(messages) == 0:
                    continue

                analysed += 1
                for message in messages:
                    creation_time = datetime.datetime.fromtimestamp(message["dt"])
                    time_bins[creation_time.date().isoformat()] += 1
                    message_count += 1

        if len(time_bins) < 2:
            return await ctx.channel.messages.send(":x: Not enough data.")

        embed = Embed(title="GCHQ")
        embed.colour = random.randint(0, 0xffffff)
        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.description = f"Tracked {analysed} members out of {len(members)} (skipped {skipped})."
        embed.add_field(name="Message Count", value=str(message_count), inline=False)
        most_active = time_bins.most_common(1)[0]
        embed.add_field(name="Most Active Day", value=str(most_active[0]))
        embed.add_field(name="Most Active Day (msgs)", value=str(most_active[1]))
        # special logic to ensure the least active is not flagged as today
        least_actives = time_bins.most_common()
        least_actives = [least_actives[-1], least_actives[-2]]
        if least_actives[0][0] == datetime.datetime.utcnow().date().isoformat():
            least_active = least_actives[1]
        else:
            least_active = least_actives[0]

        embed.add_field(name="Least Active Day", value=(str(least_active[0])))
        embed.add_field(name="Least Active Day (msgs)", value=str(least_active[1]))
        return await ctx.channel.messages.send(embed=embed)

    async def get_member_activity_data(self, guild: Guild):
        """
        Gets member activity data.
        """
        members = guild.members.values()
        redis: RedisInterface = self.client.redis
        activity_data = {}

        # Kaelin 🏀 - Today at 01:12
        # Okay, I think I have a "post total to beat" for someone to dodge the prune:
        # (11 * 1.07^DaysInactive - 30)

        # make it fair by pre-computing the date
        now = datetime.datetime.utcnow()
        for member in members:
            # skip protected users
            if member.user.bot:
                continue

            messages = await redis.get_messages(member.user)
            # ignore flagged members
            if messages == redis.FLAGGED:
                activity_data[member] = None
                continue

            messages = sorted(messages, key=lambda m: m['dt'], reverse=True)
            try:
                first_message = messages[0]
            except IndexError:
                # no messages
                activity_data[member] = ActivityReport(active=False, algo_result=0.0,
                                                       post_count=0, last_message=None)
                continue

            last_post = datetime.datetime.fromtimestamp(first_message['dt'])
            days_inactive = (now - last_post).days
            algorithm = (11 * np.math.pow(1.07, days_inactive) - 30)
            # print(member.name, len(messages), algorithm, last_post.isoformat())
            report = ActivityReport(active=len(messages) > algorithm,
                                    algo_result=algorithm, post_count=len(messages),
                                    last_message=last_post,
                                    days_inactive=days_inactive)

            # forcibly flip the activity bool
            if member.guild_permissions.kick_members:
                report.active = True

            if (now - member.joined_at).days < 3:
                report.active = True

            activity_data[member] = report

        return activity_data

    @activity.subcommand(name="members")
    async def activity_members(self, ctx: Context):
        """
        Analyses the activity of members.
        """
        members = ctx.guild.members.values()

        now = datetime.datetime.utcnow()
        async with ctx.channel.typing:
            activity_data = await self.get_member_activity_data(ctx.guild)

        em = Embed(title="Activity Report")
        skipped = sum(x is None for x in activity_data.values())
        active = sum(x.active for x in activity_data.values())
        em.description = f"Evaluated {len(members)} members. For privacy reasons, I cannot " \
                         f"determine the activity of {skipped} member(s)."
        em.set_thumbnail(url=ctx.guild.icon_url)
        em.add_field(name="Active Count", value=str(active))
        em.add_field(name="Inactive Count", value=str(len(activity_data) - active))
        em.set_footer(text="This is accurate to two weeks.")
        em.timestamp = now
        em.colour = random.randint(0, 0xffffff)
        await ctx.channel.messages.send(embed=em)

    @activity.subcommand()
    @condition(prune_condition)
    async def report(self, ctx: Context):
        """
        Produces a membership activity report.
        """
