"""
Role-me cog.
"""
import discord
from discord.ext import commands

from joku.bot import Context
from joku.checks import has_permissions
from joku.cogs._common import Cog


class Roleme(Cog):
    async def on_guild_role_delete(self, role: discord.Role):
        # automatically remove it from the roleme roles if applicable
        await self.bot.database.remove_roleme_role(role)

    @commands.group(invoke_without_command=True)
    async def roleme(self, ctx: Context, *, role: discord.Role = None):
        """
        Assigns a role to you from a list of available roles.
        """
        roles = await ctx.bot.database.get_roleme_roles(ctx.guild)
        if role is None:
            msg = "**Roles you can give yourself**:\n\n"
            for role in roles:
                msg += "- `{}`\n".format(role.name)

            await ctx.send(msg)
            return

        if role not in roles:
            await ctx.send(":x: You cannot be assigned this role.")
            return

        member = ctx.author  # type: discord.Member
        await member.add_roles(role)
        await ctx.send(":heavy_check_mark: Given you the `{}` role.".format(role.name))

    @roleme.command()
    @has_permissions(manage_roles=True)
    async def add(self, ctx: Context, *, name: str):
        """
        Creates a new role that users can be given.
        """
        guild = ctx.guild  # type: discord.Guild
        role = await guild.create_role(name=name, permissions=discord.Permissions.none())
        await ctx.bot.database.add_roleme_role(role)
        await ctx.send(":heavy_check_mark: Created new roleme role `{}`.".format(name))

    @roleme.command()
    @has_permissions(manage_roles=True)
    async def enable(self, ctx: Context, *, role: discord.Role):
        """
        Adds a role to the list of roles that can be given.
        """
        if role >= ctx.guild.me.top_role:
            await ctx.send(":x: I cannot assign this role to members.")
            return

        await ctx.bot.database.add_roleme_role(role)
        await ctx.send(":heavy_check_mark: Added `{}` as a roleme role.".format(role.name))

    @roleme.command()
    @has_permissions(manage_roles=True)
    async def disable(self, ctx: Context, *, role: discord.Role):
        """
        Removes a role from the list of roles that can be given.
        """
        await ctx.bot.database.remove_roleme_role(role)
        await ctx.send(":heavy_check_mark: Removed `{}` as a roleme role.".format(role.name))

    @commands.command()
    async def unroleme(self, ctx: Context, *, role: discord.Role):
        """
        Removes a previously assigned role.
        """
        roles = await ctx.bot.database.get_roleme_roles(ctx.guild)
        if role not in roles:
            await ctx.send(":x: Cannot remove this role.")
            return

        if role not in ctx.author.roles:
            await ctx.send(":x: You do not have this role.")
            return

        await ctx.author.remove_roles(role)
        await ctx.send(":heavy_check_mark: Removed `{}` from your roles.".format(role.name))

    @commands.group(invoke_without_command=True, aliases=["colorme"])
    async def colourme(self, ctx: Context, *, colour: discord.Colour):
        """
        Sets your custom colour.
        """
        enabled = await ctx.bot.database.get_setting(ctx.guild, "colourme_enabled", {"value": False})
        if not enabled["value"] is True:
            await ctx.send(":x: Colourme is not enabled on this server.")
            return

        guild = ctx.guild  # type: discord.Guild

        role_id = await ctx.bot.database.get_colourme_role(ctx.author)
        role = discord.utils.get(guild.roles, id=role_id)  # type: discord.Role

        role_name = "Colour for {}".format(ctx.author.name[:15])

        if not role:
            role = await guild.create_role(name=role_name,
                                           permissions=discord.Permissions.none(),
                                           colour=colour)
            await ctx.author.add_roles(role)
        else:
            await role.edit(colour=colour)

        await ctx.bot.database.set_colourme_role(ctx.author, role)

        # Add the role anyway.
        await ctx.send(":heavy_check_mark: Updated your colour role to `{}`.".format(str(colour)))

    @colourme.command()
    @has_permissions(manage_roles=True)
    async def enable(self, ctx: Context):
        """
        Enables colourme for this server.
        """
        await ctx.bot.database.set_setting(ctx.guild, "colourme_enabled", value=True)
        await ctx.send(":heavy_check_mark: Enabled colourme.")

    @colourme.command()
    @has_permissions(manage_roles=True)
    async def disable(self, ctx: Context):
        """
        Disables colourme for this server.
        """
        await ctx.bot.database.set_setting(ctx.guild, "colourme_enabled", value=False)
        await ctx.send(":heavy_check_mark: Disabled colourme.")


setup = Roleme.setup
