"""
Fake stock market system.
"""
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import has_permissions


class Stocks(Cog):
    """
    A fake stocks system.
    """
    @commands.command(name="setup")
    @has_permissions(manage_server=True)
    async def _setup(self, ctx: Context):
        """
        Enables stocks for this server.
        """


