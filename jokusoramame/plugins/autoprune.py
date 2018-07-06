"""
Autoprune functionality.
"""
import collections
import datetime
import numpy as np
import random
from curious import Embed, Guild, Member
from curious.commands import Context, Plugin, command, condition
from dataclasses import dataclass
from io import StringIO
from typing import Dict

from jokusoramame.redis import RedisInterface


@dataclass
class ActivityReport:
    active: bool
    algo_result: float
    post_count: int
    last_message: datetime.datetime
    days_inactive: int = 0


def prune_condition(ctx: Context):
    # backdoor tm
    # TODO: integrate full permissions backdoor
    return ctx.author.guild_permissions.kick_members or ctx.author.id == 214796473689178133


class Autoprune(Plugin):
    """
    Handles better automatic pruning.
    """

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

    async def get_member_activity_data(self, guild: Guild) \
            -> Dict[Member, ActivityReport]:
        """
        Gets member activity data.
        """
        members = guild.members.values()
        redis: RedisInterface = self.client.redis
        activity_data = collections.OrderedDict()

        # Kaelin 🏀 - Today at 01:12
        # Okay, I think I have a "post total to beat" for someone to dodge the prune:
        # (11 * 1.07^DaysInactive - 30)

        #
        # Kaelin 💀 - Today at 19:40
        # // Users are inactive if they've never posted and have been here for
        #  a week. if (Posts == 0) and (DaysSinceJoin > 7) then [return inactive]; // Users are
        # inactive if they haven't posted in a long time, with grace extended to "prolific"
        # users.  PostCount capped at 5000 to protect the bot's sanity. if (1.8 * 1.09 ^
        # DaysSinceLastPost - 26) > PostCount then [return inactive]; return active;

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

            days_joined = (now - member.joined_at).days

            messages = sorted(messages, key=lambda m: m['dt'], reverse=True)
            try:
                first_message = messages[0]
            except IndexError:
                # no messages
                active = days_joined < 7
                activity_data[member] = ActivityReport(active=active, algo_result=0.0,
                                                       post_count=0, last_message=None)
                continue

            last_post = datetime.datetime.fromtimestamp(first_message['dt'])
            days_inactive = (now - last_post).days
            algorithm = (1.8 * np.math.pow(1.09, days_inactive) - 26)
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

        items = list(activity_data.items())
        items = sorted(items, key=lambda i: getattr(i[1], "days_inactive", 0))
        return collections.OrderedDict(items)

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
        active = sum(x.active for x in activity_data.values() if x is not None)
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
        async with ctx.channel.typing:
            activity_data = await self.get_member_activity_data(ctx.guild)

        active_buf = StringIO()
        inactive_buf = StringIO()
        for member, report in activity_data.items():
            if report is None:
                continue

            if report.last_message is None:
                s = f"{member.name} ({member.user.username}#{member.user.discriminator}) - no data"
                s += '\n'
            else:
                s = (f"{member.name} ({member.user.username}#{member.user.discriminator}) - "
                     f"score: {report.algo_result} - last post: {report.last_message.isoformat()} -"
                     f" post count: {report.post_count} - days inactive: {report.days_inactive}")
                s += '\n'

            if report is None or report.active:
                buf = active_buf
            else:
                buf = inactive_buf

            buf.write(s)

        message_buf = StringIO()
        message_buf.write("Active users:\n\n")
        active_buf.seek(0)
        message_buf.write(active_buf.read())
        message_buf.write('\n')
        message_buf.write("Inactive users:\n\n")
        inactive_buf.seek(0)
        message_buf.write(inactive_buf.read())
        message_buf.seek(0)
        await ctx.channel.messages.send("DMing you the activity report. Please ensure you have "
                                        "DMs enabled for this server.")
        channel = await ctx.author.user.open_private_channel()
        await channel.messages.upload(fp=message_buf, filename="activity_report.txt")
