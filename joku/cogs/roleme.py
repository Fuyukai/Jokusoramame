"""
Role-me cog.
"""
import discord
from discord.ext import commands
from discord.ext.commands import bot_has_permissions

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import has_permissions, mod_command


class Roleme(Cog):
    async def on_guild_role_delete(self, role: discord.Role):
        # automatically remove it from the roleme roles if applicable
        await self.bot.database.remove_roleme_role(role)

    @commands.group(invoke_without_command=True)
    @bot_has_permissions(manage_roles=True)
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

        if role in member.roles:
            await ctx.send(":x: You already have this role.")
            return

        await member.add_roles(role)
        await ctx.send(":heavy_check_mark: Given you the `{}` role.".format(role.name))

    @roleme.command()
    @has_permissions(manage_roles=True)
    @mod_command()
    async def add(self, ctx: Context, *, name: str):
        """
        Creates a new role that users can be given.
        """
        guild = ctx.guild  # type: discord.Guild
        role = await guild.create_role(name=name, permissions=discord.Permissions.none())
        await ctx.bot.database.add_roleme_role(role)
        await ctx.send(":heavy_check_mark: Created new roleme role `{}`.".format(name))

    @roleme.command(name="enable")
    @has_permissions(manage_roles=True)
    @mod_command()
    async def _enable(self, ctx: Context, *, role: discord.Role):
        """
        Adds a role to the list of roles that can be given.
        """
        if role >= ctx.guild.me.top_role:
            await ctx.send(":x: I cannot assign this role to members.")
            return

        await ctx.bot.database.add_roleme_role(role)
        await ctx.send(":heavy_check_mark: Added `{}` as a roleme role.".format(role.name))

    @roleme.command(name="disable")
    @has_permissions(manage_roles=True)
    @mod_command()
    async def _disable(self, ctx: Context, *, role: discord.Role):
        """
        Removes a role from the list of roles that can be given.
        """
        await ctx.bot.database.remove_roleme_role(role)
        await ctx.send(":heavy_check_mark: Removed `{}` as a roleme role.".format(role.name))

    @commands.command()
    @bot_has_permissions(manage_roles=True)
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
    @bot_has_permissions(manage_roles=True)
    async def colourme(self, ctx: Context, *, colour: discord.Colour=None):
        """
        Sets your custom colour.
        """
        enabled = await ctx.bot.database.get_setting(ctx.guild, "colourme_enabled", {"enabled": False})
        if not enabled["enabled"] is True:
            await ctx.send(":x: Colourme is not enabled on this server.")
            return

        if colour is None:
            role = await ctx.bot.database.get_colourme_role(ctx.author)
            if role:
                await ctx.send("Your colour is **`{}`**.".format(str(role.colour)))
            else:
                await ctx.send(":x: You have no colour role.")

            return

        guild = ctx.guild  # type: discord.Guild

        role = await ctx.bot.database.get_colourme_role(ctx.author)

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
    @mod_command()
    async def enable(self, ctx: Context):
        """
        Enables colourme for this server.
        """
        await ctx.bot.database.set_setting(ctx.guild, "colourme_enabled", enabled=True)
        await ctx.send(":heavy_check_mark: Enabled colourme.")

    @colourme.command()
    @has_permissions(manage_roles=True)
    @mod_command()
    async def disable(self, ctx: Context):
        """
        Disables colourme for this server.
        """
        await ctx.bot.database.set_setting(ctx.guild, "colourme_enabled", enabled=False)
        await ctx.send(":heavy_check_mark: Disabled colourme.")


setup = Roleme.setup
