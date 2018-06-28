"""
Colourme plugin.
"""
from curious import Role
from curious.commands import Context, Plugin, command, condition

from jokusoramame.plugins.roles.roleme_shared import RolemeResult, RolemeShared


class ColourMe(Plugin):
    """
    Like RoleMe, but for colour roles.
    """
    def __init__(self, client):
        super().__init__(client)
        self.impl = RolemeShared(client)

    @command()
    async def colorme(self, ctx: Context):
        """
        No.
        """
        return await ctx.channel.messages.send("I don't speak :flag_us: Simplified English.")

    @command()
    async def colourme(self, ctx: Context, *, role: Role = None):
        """
        Adds a colour role to your list of roles.
        """
        roles = await self.impl.get_all_roleme_roles(ctx.guild, colourme=True)

        # behaviour a, assign a role
        if role is not None:
            await ctx.author.roles.remove(*[r for r in roles if r in ctx.author.roles])

            result = await self.impl.apply_roleme_role(role, ctx.author)
            if result is RolemeResult.ERR_NOT_ASSIGNABLE:
                return await ctx.channel.messages.send(":x: This role is not self-assignable.")

            return await ctx.channel.messages.send(":heavy_check_mark: Assigned you this colour.")
        else:
            if not roles:
                return await ctx.channel.messages.send(":pencil: There are no colour you can "
                                                       "assign yourself in this server currently.")

            fmts = []
            for role in roles:
                fmts.append(" - {}".format(role.name))

            role_list = '\n'.join(fmts)
            return await ctx.channel.messages.send(f":pencil: **Colours you can give yourself:**"
                                                   f"\n\n{role_list}")

    @colourme.subcommand()
    @condition(lambda ctx: ctx.author.guild_permissions.manage_roles)
    async def add(self, ctx: Context, *, role: Role = None):
        """
        Adds a role as a colourme role.
        """
        await self.impl.add_roleme_role(role, is_colourme=True)
        await ctx.channel.messages.send(f":heavy_check_mark: Added {role.name} as a colourme role.")

    @colourme.subcommand()
    @condition(lambda ctx: ctx.author.guild_permissions.manage_roles)
    async def remove(self, ctx: Context, *, role: Role = None):
        """
        Removes a role as a colourme role.
        """
        await self.impl.remove_roleme_role(role)
        await ctx.channel.messages.send(f":heavy_check_mark: Removed {role.name} as a colourme "
                                        f"role.")

    @colourme.subcommand()
    async def uncolourme(self, ctx: Context, *, role: Role):
        """
        Removes a role from you.
        """
        result = await self.impl.unapply_roleme_role(role, ctx.author)
        if result is result.ERR_NOT_ASSIGNABLE:
            return await ctx.channel.messages.send(":x: This colour is not self-assignable.")

        await ctx.channel.messages.send(":heavy_check_mark: Removed you from this colour.")

    @command(name="uncolourme")
    async def uncolourme_toplevel(self, ctx: Context, *, role: Role):
        return await self.uncolourme(ctx, role=role)
