"""
TODO-list module.
"""
import discord
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.utils import paginate_table


class Todos(Cog):
    @commands.group(pass_context=True, invoke_without_command=True)
    async def todo(self, ctx: Context, *, target: discord.Member = None):
        """
        Views your TODO list.

        If you target a specific member, you can see their TODO list.
        """
        if target is None:
            target = ctx.message.author
        todos = await ctx.bot.database.get_user_todos(target)

        # M O R E T A B L E S
        headers = ["Priority", "Content"]
        rows = []

        header = "\U0001f4d4 | **TODO List for {}**:\n\n".format(target.display_name)

        for item in todos:
            rows.append([item["priority"], item["content"]])

        pages = paginate_table(rows, headers)

        await ctx.channel.send(header)
        for page in pages:
            await ctx.channel.send(page)

    @todo.command(pass_context=True)
    async def add(self, ctx: Context, *, content: str):
        """
        Adds something to your TODO list.
        """
        i = await ctx.bot.database.add_user_todo(ctx.message.author, content)
        # Get the new priority from the changes.
        priority = i["changes"][0]["new_val"]["priority"]
        await ctx.channel.send(":heavy_check_mark: Added TODO item `{}`.".format(priority))

    @todo.command(pass_context=True)
    async def remove(self, ctx: Context, *, index: int):
        """
        Removes an item from your TODO list.
        """
        if index < 1:
            await ctx.channel.send(":x: Indexes must be above zero.")
            return
        i = await ctx.bot.database.delete_user_todo(ctx.message.author, index)

        removed = i[0]
        if removed["deleted"] == 0:
            await ctx.channel.send(":x: Could not remove item.")
            return

        await ctx.channel.send(":heavy_check_mark: Removed item at index `{}`.".format(index))


def setup(bot):
    bot.add_cog(Todos(bot))
