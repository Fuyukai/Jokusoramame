"""
Specific checks.
"""
from discord.ext.commands import CheckFailure


def is_owner(ctx):
    if not ctx.bot.owner_id == ctx.message.author.id:
        raise CheckFailure(message="You are not the owner.")
    return True
