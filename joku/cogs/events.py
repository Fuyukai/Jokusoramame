"""
Cog that handles event listeners and such.
"""
import discord

import rethinkdb as r
from discord.ext import commands
import tabulate

from joku.bot import Jokusoramame, Context


class Events(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

    @commands.command(pass_context=True)
    async def events(self, ctx: Context):
        """
        Shows the top 10 most frequent events.
        """
        headers = ("Event", "Frequency")
        data = ctx.bot.manager.events.most_common(10)

        table = tabulate.tabulate(data, headers=headers, tablefmt="orgtbl")

        await ctx.bot.say("```{}```".format(table))

    async def on_socket_response(self, data: dict):
        """
        Adds events to the event counter.
        """
        event = data.get("t")
        if not event:
            self.bot.logger.warning("Caught None-event: {}".format(data))
            return
        self.bot.manager.events[event] += 1

    async def on_member_join(self, member: discord.Member):
        """
        Called when a member joins.

        Checks if this server is subscribed to joins, and formats the welcome message as appropriate.
        """

        channel, event_msg = await self.bot.rethinkdb.get_event_message(member.server,
                                                                        "joins",
                                                                        "Welcome {member.name}!"
                                                                        )
        msg = event_msg.format(**{
            "member": member,
            "server": member.server,
            "channel": channel
        })
        await self.bot.send_message(channel, msg)

    async def on_member_remove(self, member: discord.Member):
        channel, event_msg = await self.bot.rethinkdb.get_event_message(member.server,
                                                                        "leaves",
                                                                        "Bye {member.name}!"
                                                                        )
        msg = event_msg.format(**{
            "member": member,
            "server": member.server,
            "channel": channel
        })
        await self.bot.send_message(channel, msg)


def setup(bot: Jokusoramame):
    bot.add_cog(Events(bot))
