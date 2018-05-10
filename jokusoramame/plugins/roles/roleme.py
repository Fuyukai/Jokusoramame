"""
Roleme stuff.
"""

from curious import Role
from curious.commands import Context, Plugin, command, condition

from jokusoramame.plugins.roles.roleme_shared import RolemeResult, RolemeShared


class Roleme(Plugin):
    """
    Commands for the roleme portion of the bot.
    """
    def __init__(self, client):
        super().__init__(client)
        self.impl = RolemeShared(client)

    @command()
    async def roleme(self, ctx: Context, *, role: Role = None):
        """
        Adds a role to your list of roles.
        """
        roles = await self.impl.get_all_roleme_roles(ctx.guild)

        # behaviour a, assign a role
        if role is not None:
            result = await self.impl.apply_roleme_role(role, ctx.author)
            if result is RolemeResult.ERR_NOT_ASSIGNABLE:
                return await ctx.channel.messages.send(":x: This role is not self-assignable.")

            return await ctx.channel.messages.send(":heavy_check_mark: Assigned you this role.")
        else:
            if not roles:
                return await ctx.channel.messages.send(":pencil: There are no roles you can assign "
                                                       "yourself in this server currently.")

            fmts = []
            for role in roles:
                fmts.append(" - {}".format(role.name))

            role_list = '\n'.join(fmts)
            return await ctx.channel.messages.send(f":pencil: **Roles you can give yourself:**"
                                                   f"\n\n{role_list}")

    @roleme.subcommand()
    @condition(lambda ctx: ctx.author.guild_permissions.manage_roles)
    async def add(self, ctx: Context, *, role: Role = None):
        """
        Adds a role as a roleme role.
        """
        await self.impl.add_roleme_role(role, is_colourme=False)
        await ctx.channel.messages.send(f":heavy_check_mark: Added {role.name} as a roleme role.")

    @roleme.subcommand()
    @condition(lambda ctx: ctx.author.guild_permissions.manage_roles)
    async def remove(self, ctx: Context, *, role: Role = None):
        """
        Removes a role as a roleme role.
        """
        await self.impl.remove_roleme_role(role)
        await ctx.channel.messages.send(f":heavy_check_mark: Removed {role.name} as a roleme role.")

    @roleme.subcommand()
    async def unroleme(self, ctx: Context, *, role: Role):
        """
        Removes a role from you.
        """
        result = await self.impl.unapply_roleme_role(role, ctx.author)
        if result is result.ERR_NOT_ASSIGNABLE:
            return await ctx.channel.messages.send(":x: This role is not self-assignable.")

        await ctx.channel.messages.send(":heavy_check_mark: Removed you from this role.")

    @command(name="unroleme")
    async def unroleme_toplevel(self, ctx: Context, *, role: Role):
        return await self.unroleme(ctx, role=role)
