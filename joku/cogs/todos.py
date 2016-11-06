"""
TODO-list module.
"""
import discord
from discord.ext import commands

from joku.bot import Jokusoramame, Context
from joku.utils import paginate_table


class Todos(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

    @commands.group(pass_context=True, invoke_without_command=True)
    async def todo(self, ctx: Context, *, target: discord.Member = None):
        """
        Views your TODO list.

        If you target a specific member, you can see their TODO list.
        """
        if target is None:
            target = ctx.message.author
        todos = await ctx.bot.rethinkdb.get_user_todos(target)

        # M O R E T A B L E S
        headers = ["Priority", "Content"]
        rows = []

        header = "\U0001f4d4 | **TODO List for {}**:\n\n".format(target.display_name)

        for item in todos:
            rows.append([item["priority"], item["content"]])

        pages = paginate_table(rows, headers)

        await ctx.bot.say(header)
        for page in pages:
            await ctx.bot.say(page)

    @todo.command(pass_context=True)
    async def add(self, ctx: Context, *, content: str):
        """
        Adds something to your TODO list.
        """
        i = await ctx.bot.rethinkdb.add_user_todo(ctx.message.author, content)
        # Get the new priority from the changes.
        priority = i["changes"][0]["new_val"]["priority"]
        await ctx.bot.say(":heavy_check_mark: Added TODO item `{}`.".format(priority))

    @todo.command(pass_context=True)
    async def remove(self, ctx: Context, *, index: int):
        """
        Removes an item from your TODO list.
        """
        if index < 1:
            await ctx.bot.say(":x: Indexes must be above zero.")
            return
        i = await ctx.bot.rethinkdb.delete_user_todo(ctx.message.author, index)

        removed = i[0]
        if removed["deleted"] == 0:
            await ctx.bot.say(":x: Could not remove item.")
            return

        await ctx.bot.say(":heavy_check_mark: Removed item at index `{}`.".format(index))


def setup(bot):
    bot.add_cog(Todos(bot))
