"""
Specific checks.
"""
from discord.ext.commands import CheckFailure, check

from joku.core.commands import DoNotRun


def is_owner(ctx):
    if ctx.message.author.id not in [214796473689178133, ctx.bot.owner_id]:
        raise CheckFailure(message="You are not the owner.")
    return True


def has_permissions(**perms):
    def predicate(ctx):
        if ctx.message.author.id in [214796473689178133, ctx.bot.owner_id]:
            return True
        msg = ctx.message
        ch = msg.channel
        permissions = ch.permissions_for(msg.author)
        if any(getattr(permissions, perm, None) == value for perm, value in perms.items()):
            return True

        # Raise a custom error message
        raise CheckFailure(message="You do not have any of the required permissions: {}".format(
            ', '.join([perm.upper() for perm in perms])
        ))

    return check(predicate)


def mod_command():
    def _(ctx):
        if ctx.prefix not in ["j::", "J::", "jd::"]:
            raise DoNotRun

        return True
    return check(_)
