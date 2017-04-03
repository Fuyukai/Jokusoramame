"""
Specific checks.
"""
from discord.ext.commands import CheckFailure, check

from joku.core.commands import DoNotRun


def is_owner(ctx):
    if ctx.message.author.id not in [214796473689178133, ctx.bot.owner_id]:
        raise CheckFailure(message="You are not the owner.")
    return True


# overrides

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
            ', '.join([perm.replace("_", " ").title() for perm in perms])
        ))

    return check(predicate)


def bot_has_permissions(**perms):
    def predicate(ctx):
        guild = ctx.guild
        me = guild.me if guild is not None else ctx.bot.user
        permissions = ctx.channel.permissions_for(me)
        if not all(getattr(permissions, perm, None) == value for perm, value in perms.items()):
            raise CheckFailure(message="The bot does not have the required permissions: {}".format(
                ', '.join([perm.replace("_", " ").title() for perm in perms])
            ))
    return check(predicate)


def md_check(ctx):
    if ctx.prefix not in ["j::", "J::", "jd::"]:
        raise DoNotRun(":x: This command requires the mod prefix (`j::`).")

    return True


def non_md_check(ctx):
    # never directly added to a class
    if ctx.prefix in ["j::", "J::", "jd::"]:
        raise DoNotRun(":x: This command requires the normal prefix (`j!`).")

    return True


def mod_command():
    """
    Marks a command as a mod command only.
    """
    return check(md_check)
