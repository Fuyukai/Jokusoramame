"""
Configuration cog.
"""
import argparse
import shlex

import discord
from discord.ext import commands
from discord.ext.commands import MemberConverter, BadArgument, TextChannelConverter

from joku.bot import Jokusoramame, Context
from joku.cogs._common import Cog
from joku.checks import has_permissions
from joku.utils import get_role


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # raise the exception instead of printing it
        raise Exception(message)


class Config(Cog):
    @commands.command(pass_context=True)
    @has_permissions(manage_server=True, manage_messages=True)
    async def inviscop(self, ctx: Context, *, status: str = None):
        """
        Manages the Invisible cop

        The Invisible Cop automatically deletes any messages of users with Invisible on.
        """
        if status is None:
            # Check the status.
            setting = await ctx.bot.database.get_setting(ctx.message.guild, "dndcop", {})
            if setting.get("status") == 1:
                await ctx.channel.send("Invis Cop is currently **on.**")
            else:
                await ctx.channel.send("Invis Cop is currently **off.**")
        else:
            if status.lower() == "on":
                await ctx.bot.database.set_setting(ctx.message.guild, "dndcop", status=1)
                await ctx.channel.send(":heavy_check_mark: Turned Invis Cop on.")
                return
            elif status.lower() == "off":
                await ctx.bot.database.set_setting(ctx.message.guild, "dndcop", status=0)
                await ctx.channel.send(":heavy_check_mark: Turned Invis Cop off.")
                return
            else:
                await ctx.channel.send(":x: No.")

    @commands.group(pass_context=True, invoke_without_command=True)
    @has_permissions(manage_server=True, manage_roles=True)
    async def rolestate(self, ctx: Context, *, status: str = None):
        """
        Manages rolestate.

        This will automatically save roles for users who have left the server.
        """
        if status is None:
            # Check the status.
            setting = await ctx.bot.database.get_setting(ctx.message.guild, "rolestate", {})
            if setting.get("status") == 1:
                await ctx.channel.send("Rolestate is currently **on.**")
            else:
                await ctx.channel.send("Rolestate is currently **off.**")
        else:
            if status.lower() == "on":
                await ctx.bot.database.set_setting(ctx.message.guild, "rolestate", status=1)
                await ctx.channel.send(":heavy_check_mark: Turned Rolestate on.")
                return
            elif status.lower() == "off":
                await ctx.bot.database.set_setting(ctx.message.guild, "rolestate", status=0)
                await ctx.channel.send(":heavy_check_mark: Turned Rolestate off.")
                return
            else:
                await ctx.channel.send(":x: No.")

    @rolestate.command()
    async def view(self, ctx: Context, *, user_id: int = None):
        """
        Views the current rolestate of a member.
        """
        if user_id is None:
            user_id = ctx.author.id

        rolestate = await self.bot.database.get_rolestate_for_id(ctx.guild.id, user_id)
        user = await ctx.bot.get_user_info(user_id)  # type: discord.User

        em = discord.Embed(title="Rolestate viewer")

        if rolestate is None:
            em.description = "**No rolestate found for this user here.**"
            em.colour = discord.Colour.red()
        else:
            em.description = "This shows the most recent rolestate for a user ID. This is **not accurate** if they " \
                             "haven't left before, or are still in the guild."

            em.add_field(name="Username", value=user.name)

            em.add_field(name="Nick", value=rolestate.nick, inline=False)
            roles = ", ".join([get_role(ctx.guild, r_id).mention for r_id in rolestate.roles if r_id != ctx.guild.id])
            em.add_field(name="Roles", value=roles, inline=False)

            em.colour = discord.Colour.light_grey()

        em.set_thumbnail(url=user.avatar_url)
        em.set_footer(text="Rolestate for guild {}".format(ctx.guild.name))

        await ctx.send(embed=em)


def setup(bot):
    bot.add_cog(Config(bot))
