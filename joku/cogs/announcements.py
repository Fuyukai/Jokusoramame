import re

import discord
from discord import TextChannel, HTTPException
from discord.ext import commands

from joku.cogs._common import Cog
from joku.core import checks
from joku.core.bot import Context
from joku.core.checks import mod_command


class Announcements(Cog):
    """
    Commands for bulletins and announcements.
    """
    @commands.group(pass_context=True, invoke_without_command=True)
    @checks.has_permissions(manage_guild=True)
    @mod_command()
    async def bulletin(self, ctx: Context, channel: TextChannel):
        """
        Creates a new bulletin message.
        
        This message can be edited by anybody with
        Manage Server permissions or Administrator.
        
        This message can effectively be used to create
        an admin-editable info message, or similar.
        """
        guild = await ctx.bot.database.get_or_create_guild(ctx.guild)

        async def _make_message():
            msg = await channel.send("\U00002714 {.mention}, this is the new **bulletin message**. \n"
                                     "Use `j::bulletin edit` to edit the content of this new message."
                                     .format(ctx.author))

            await ctx.bot.database.update_bulletin_message(ctx.guild, channel, msg.id)

        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.send(":x: I need Send Messages in that channel.")
            return

        if guild.bulletin_message is None:
            # make the new bulletin message
            await _make_message()
            return

        try:
            message = await channel.get_message(guild.bulletin_message)
        except HTTPException:
            await _make_message()
        else:
            await ctx.send(":x: This guild already has a bulletin message.")

    @bulletin.command()
    @checks.has_permissions(manage_guild=True)
    @mod_command()
    async def get(self, ctx: Context):
        """
        Gets the current content of the bulletin message.
        """
        guild = await ctx.bot.database.get_or_create_guild(ctx.guild)

        if guild.bulletin_message is None:
            await ctx.send(":x: There is no bulletin message in this guild.")
            return

        # https://github.com/Rapptz/RoboDanny/blob/master/cogs/tags.py#L155-L174
        # thank u danny
        transformations = {
            re.escape(c): '\\' + c
            for c in ('*', '`', '_', '~', '\\', '<')
        }

        def replace(obj):
            return transformations.get(re.escape(obj.group(0)), '')

        pattern = re.compile('|'.join(transformations.keys()))

        try:
            channel = ctx.guild.get_channel(guild.bulletin_channel)
            message = await channel.get_message(guild.bulletin_message)
        except Exception:
            await ctx.send(":x: Either the message or channel could not be found (deleted?). "
                           "Use `j::bulletin delete` to reset the bulletin.")
            return

        msg = pattern.sub(replace, message.content)
        await ctx.send(msg)

    @bulletin.command()
    @checks.has_permissions(manage_guild=True)
    @mod_command()
    async def edit(self, ctx: Context, *, new_content: str):
        """
        Edits the current bulletin message.
        """
        guild = await ctx.bot.database.get_or_create_guild(ctx.guild)

        if guild.bulletin_message is None:
            await ctx.send(":x: There is no bulletin message in this guild.")
            return

        try:
            channel = ctx.guild.get_channel(guild.bulletin_channel)
            message = await channel.get_message(guild.bulletin_message)
        except Exception:
            await ctx.send(":x: Either the message or channel could not be found (deleted?). "
                           "Use `j::bulletin delete` to reset the bulletin.")
            return

        await message.edit(content=new_content)
        await ctx.send(":heavy_check_mark: Edited successfully.")

    @bulletin.command()
    @checks.has_permissions(manage_guild=True)
    @mod_command()
    async def delete(self, ctx: Context):
        """
        Deletes the current bulletin.
        """
        guild = await ctx.bot.database.get_or_create_guild(ctx.guild)

        if guild.bulletin_message is None:
            await ctx.send(":x: There is no bulletin message in this guild.")
            return

        try:
            channel = ctx.guild.get_channel(guild.bulletin_channel)
            message = await channel.get_message(guild.bulletin_message)
        except Exception:
            pass
        else:
            try:
                await message.delete()
            except:
                pass

        await ctx.bot.database.update_bulletin_message(guild, None, message_id=None)
        await ctx.send(":heavy_check_mark: Bulletin deleted.")


setup = Announcements.setup
