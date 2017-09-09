"""
Role-me cog.
"""
import discord
from asyncio_extras import threadpool
from discord.ext import commands
from discord.ext.commands import ColourConverter, RoleConverter, BadArgument
from sqlalchemy.orm import Session

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import has_permissions, mod_command, bot_has_permissions
from joku.db.tables import UserColour


class Roleme(Cog):
    async def on_guild_role_delete(self, role: discord.Role):
        # automatically remove it from the roleme roles if applicable
        await self.bot.database.remove_roleme_role(role)
        await self.bot.database.remove_colourme_role(role)

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

        if role >= ctx.guild.me.top_role:
            await ctx.send(":x: I cannot assign this role. (it is above my highest role)")
            return

        try:
            await member.add_roles(role)
        except discord.Forbidden:
            await ctx.send(":x: Forbidden. Fix the fuckin roles")
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
    async def colourme(self, ctx: Context, *, choice: str = None):
        """
        Sets your custom colour.
        """
        modchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                               "colourme_modchoice_enabled")

        userchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                                "colourme_userchoice_enabled")

        if userchoice_enabled == 'True':
            # Regular colorme functionality
            c = ColourConverter()
            c.prepare(ctx, choice)
            colour = c.convert()
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

            msg = ":heavy_check_mark: Updated your colour role to `{}`."
            if not role:
                if len(ctx.guild.roles) >= 200:
                    await ctx.send(":x: This server has too many roles (>= 200).")
                    return

                role = await guild.create_role(name=role_name,
                                               permissions=discord.Permissions.none(),
                                               colour=colour)
                await ctx.author.add_roles(role)
            else:
                if colour.value == 0:
                    await role.delete()
                    msg = ":heavy_check_mark: Deleted your colour role."
                else:
                    await role.edit(colour=colour)

            await ctx.bot.database.set_colourme_role(ctx.author, role)

            # Add the role anyway.
            await ctx.send(msg.format(str(colour)))
            return

        if modchoice_enabled == 'True':
            # New modchoice colourme functionality... yes it is just the roleme stuff.
            roles = await ctx.bot.database.get_colourme_roles(ctx.guild)

            c = RoleConverter()
            c.prepare(ctx, choice)
            try:
                role = c.convert()
            except (TypeError, BadArgument):
                role = None

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

            new_roles = [r for r in member.roles if r not in roles] + [role]

            await member.edit(roles=new_roles)
            await ctx.send(":heavy_check_mark: Given you the `{}` role.".format(role.name))
            return

        await ctx.send(":x: Colourme is not enabled on this server.")

    @commands.command()
    @bot_has_permissions(manage_roles=True)
    async def uncolourme(self, ctx: Context, *, role: discord.Role):
        """
        Removes a previously assigned role.
        """
        roles = await ctx.bot.database.get_colourme_roles(ctx.guild)
        if role not in roles:
            await ctx.send(":x: Cannot remove this role.")
            return

        if role not in ctx.author.roles:
            await ctx.send(":x: You do not have this role.")
            return

        await ctx.author.remove_roles(role)
        await ctx.send(":heavy_check_mark: Removed `{}` from your roles.".format(role.name))

    @colourme.command()
    @has_permissions(manage_roles=True)
    @mod_command()
    async def clean(self, ctx: Context):
        """
        Cleans out old colourme roles for users no longer in the server.
        """
        async with threadpool():
            with ctx.bot.database.get_session() as sess:
                assert isinstance(sess, Session)
                roles = sess.query(UserColour).filter(UserColour.guild_id == ctx.guild.id).all()

        modchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                               "colourme_modchoice_enabled")
        removed = []
        async with ctx.channel.typing():
            for usercolour in roles:
                member = ctx.guild.get_member(usercolour.user_id)
                if member is None or modchoice_enabled:
                    role = ctx.guild.roles.find | (lambda r: r.id == usercolour.role_id)
                    if not role:
                        continue

                    await role.delete()
                    removed.append(role)

        rids = [role.id for role in removed]

        async with threadpool():
            with ctx.bot.database.get_session() as sess:
                assert isinstance(sess, Session)
                sess.query(UserColour).filter(UserColour.role_id.in_(rids)).delete()

        await ctx.send(":heavy_check_mark: Deleted `{}` roles.".format(len(removed)))

    @colourme.command(aliases=['add'])
    @has_permissions(manage_roles=True)
    @mod_command()
    async def addcolour(self, ctx: Context, colour: discord.Colour, *, colour_alias: str):
        """
        Adds a new colour role for users to pick from
        """

        enabled = await ctx.bot.database.get_setting(ctx.guild, "colourme_modchoice_enabled")

        if not (enabled == 'True'):
            await ctx.send(":x: Colourme mod choice is not enabled on this server.")
            return

        if colour is None:
            await ctx.send(":x: You have not provided a colour.")
            return

        if colour_alias is None:
            await ctx.send(":x: You have not provided a name for the colour.")
            return

        guild = ctx.guild  # type: discord.Guild

        colours = await ctx.bot.database.get_colourme_roles(guild)

        role_name = colour_alias

        role = await ctx.bot.database.get_colourme_role(ctx.author)

        msg = ":heavy_check_mark: Added colour role: `{}`."
        # Check if any colour alias already exists in the role list
        if not any(str(c)[9:] == colour_alias for c in colours):
            if len(ctx.guild.roles) >= 200:
                await ctx.send(":x: This server has too many roles (>= 200).")
                return

            role = await guild.create_role(name=role_name,
                                           permissions=discord.Permissions.none(),
                                           colour=colour)
            await ctx.bot.database.add_colourme_role(role)

        # Add the role anyway.
        await ctx.send(msg.format(str(colour_alias)))

    @colourme.command()
    @has_permissions(manage_roles=True)
    async def mode(self, ctx: Context):
        """
        Displays current Colourme mode
        """
        modchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                               "colourme_modchoice_enabled")
        userchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                                "colourme_userchoice_enabled")

        if userchoice_enabled == 'True':
            await ctx.send(":warning: Users may pick their own colours.")
        elif modchoice_enabled == 'True':
            await ctx.send(":warning: Mods pick the colours.")
        else:
            await ctx.send(":x: Colourme is not enabled on this server.")

    @colourme.command(aliases=['rmcolour', 'remove'])
    @has_permissions(manage_roles=True)
    @mod_command()
    async def removecolour(self, ctx: Context, *, colour_alias: str):
        """
        Removes a colour from the colour choice.
        """
        enabled = await ctx.bot.database.get_setting(ctx.guild, "colourme_modchoice_enabled")

        if enabled != 'True':
            await ctx.send(":x: Colourme mod choice is not enabled on this server.")
            return

        role = ctx.guild.roles.find | (lambda r: r.name == colour_alias)

        msg = ":heavy_check_mark: Removed colour role: `{}`."
        if role:
            await ctx.bot.database.remove_colourme_role(role)
            await role.delete()
        else:
            msg = ":x: Did not find role: `{}`."

        await ctx.send(msg.format(str(colour_alias)))

    @colourme.command()
    @has_permissions(manage_roles=True)
    @mod_command()
    async def enable(self, ctx: Context, *, opt: str = "modchoice"):
        """
        Enables colourme for this server.

        By default, enables modchoice. Adding userchoice on the end allows users to specify colours.
        """
        modchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                               "colourme_modchoice_enabled")
        userchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                                "colourme_userchoice_enabled")

        # Ensure userchoice and modchoice cannot be enabled at the same time.
        if (modchoice_enabled is not (None or 'False')) or (userchoice_enabled is not (None or 'False')):
            await ctx.send(
                ":x: Colourme already enabled. Use `j::colourme switch` to change colourme mode")
            return

        if opt == "userchoice":
            await ctx.bot.database.set_setting(ctx.guild, "colourme_userchoice_enabled", 'True')
            await ctx.send(":heavy_check_mark: Enabled colourme with user choice.")
            return
        await ctx.bot.database.set_setting(ctx.guild, "colourme_modchoice_enabled", 'True')
        await ctx.send(":heavy_check_mark: Enabled colourme with mod choice.")

    @colourme.command()
    @has_permissions(manage_roles=True)
    @mod_command()
    async def switch(self, ctx: Context):
        """
        Switches colourme mode from one mode to another.

        Make sure a responsible mod cleans up roles between switches
        """
        modchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                               "colourme_modchoice_enabled")
        userchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                                "colourme_userchoice_enabled")

        if userchoice_enabled == 'True':
            # Userchoice was enabled
            await ctx.bot.database.set_setting(ctx.guild, "colourme_userchoice_enabled", 'False')
            await ctx.bot.database.set_setting(ctx.guild, "colourme_modchoice_enabled", 'True')
            await ctx.send(":heavy_check_mark: Switched to mod choice mode.")
            return

        if modchoice_enabled == 'True':
            # Modchoice was enabled
            await ctx.bot.database.set_setting(ctx.guild, "colourme_modchoice_enabled", 'False')
            await ctx.bot.database.set_setting(ctx.guild, "colourme_userchoice_enabled", 'True')
            await ctx.send(":heavy_check_mark: switched to user choice mode.")
            return

        await ctx.send(":x: Colourme is not enabled on this server.")

    @colourme.command()
    @has_permissions(manage_roles=True)
    @mod_command()
    async def disable(self, ctx: Context):
        """
        Disables colourme for this server.
        """
        modchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                               "colourme_modchoice_enabled")
        userchoice_enabled = await ctx.bot.database.get_setting(ctx.guild,
                                                                "colourme_userchoice_enabled")

        if userchoice_enabled == 'True':
            # userchoice was enabled
            await ctx.bot.database.set_setting(ctx.guild, "colourme_userchoice_enabled", 'False')
            await ctx.send(":heavy_check_mark: Disabled colourme.")
            return

        if modchoice_enabled == 'True':
            # modchoice was enabled
            await ctx.bot.database.set_setting(ctx.guild, "colourme_modchoice_enabled", 'False')
            await ctx.send(":heavy_check_mark: Disabled colourme.")
            return

        await ctx.send(":x: Colourme is not enabled on this server.")

setup = Roleme.setup
