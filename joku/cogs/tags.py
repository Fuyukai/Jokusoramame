"""
Generic tag bot, yay.
"""
import shlex

import discord
from discord.ext import commands
from discord.ext.commands import CommandError, CommandNotFound, CommandInvokeError

from joku.bot import Jokusoramame


class Tags(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

    @commands.group(pass_context=True, invoke_without_command=True)
    async def tag(self, ctx, *, name: str):
        """
        Tags are like aliases or autoresponses that can be added to the bot.

        They are made with `tag create`, and deleted with `tag delete`.
        To be accessed, they are simply called like commands are.
        """
        tag_obb = await self.bot.rethinkdb.get_tag(ctx.message.server, name)
        if not tag_obb:
            await self.bot.say("Tag not found.")
            return

        owner = self.bot.get_member(tag_obb["owner_id"])

        tmp = {
            "name": tag_obb["name"],
            "owner": owner.name if owner else "<Unknown>",
            "lm": tag_obb["last_modified"]
        }

        # Display the tag info.
        await self.bot.say("**Tag name:** `{name}`\n"
                           "**Owner:** `{owner}`\n"
                           "**Last modified:** `{lm}`".format(**tmp))

    @tag.command(pass_context=True)
    async def create(self, ctx, name: str, *, content: str):
        """
        Creates a new tag.

        This will overwrite other tags with the same name, if you are the owner or an administrator.
        """
        existing_tag = await self.bot.rethinkdb.get_tag(ctx.message.server, name)

        if existing_tag:
            # Check for the admin perm.
            if not ctx.message.author.server_permissions.administrator:
                # Check if the owner_id matches the author id.
                if ctx.message.author.id != existing_tag["owner_id"]:
                    await self.bot.say(":x: You cannot edit somebody else's tag.")
                    return

            # Don't overwrite the owner_id.
            owner_id = existing_tag["owner_id"]
        else:
            owner_id = ctx.message.author.id

        # Replace stuff in content.
        content = content.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")

        # Set the tag.
        await self.bot.rethinkdb.save_tag(ctx.message.server, name, content, owner=owner_id)
        await self.bot.say(":heavy_check_mark: Tag **{}** saved.".format(name))

    @tag.command(pass_context=True)
    async def delete(self, ctx, *, name: str):
        """
        Deletes a tag.

        You must be the owner of the tag, or an administrator.
        """
        existing_tag = await self.bot.rethinkdb.get_tag(ctx.message.server, name)

        if not existing_tag:
            await self.bot.say(":x: This tag does not exist.")
            return

        # Check the owner_id
        if not ctx.message.author.server_permissions.administrator or existing_tag["owner_id"] != \
                ctx.message.author.id:
            await self.bot.say(":x: You do not have permission to edit this tag.")
            return

        # Now, delete the tag.
        await self.bot.rethinkdb.delete_tag(ctx.message.server, name)
        await self.bot.say(":skull_and_crossbones: Tag deleted.")

    # Unlike other bots, tags are registered like full commands.
    # So, they're entirely handled inside on_command_error.
    # This will catch the CommandNotFound, and try and find the tag.
    async def on_command_error(self, exc: CommandError, ctx):
        if not isinstance(exc, CommandNotFound):
            # We don't want to catch any non-command not found errors.
            return

        # This is mostly copy/pasted from `process_commands`

        # Try and load the tag.
        cmd = ctx.invoked_with

        # Load the tag.
        tag = await self.bot.rethinkdb.get_tag(ctx.message.server, cmd)

        if not tag:
            # The tag doesn't exist.
            return

        # Get the content from the tag.
        content = tag["content"]

        # Left strip any whtiespace.
        content = content.lstrip(" ")

        # Check if it starts with `{`.
        if content.startswith("{") and content.endswith("}"):
            # lstrip the {, and rstrip the }.
            clean_content = content.lstrip("{ ")[:-1]
            # Create a temporary dict to pass to the message.
            # Shlex split the message.
            # TODO: make this nicer.

            message_args = shlex.split(ctx.message.content)[1:]

            tmp = {
                "message": ctx.message,
                "server": ctx.message.server,
                "author": ctx.message.author,
                "channel": ctx.message.channel,
                "all": ' '.join(message_args)
            }

            # Format the string.
            try:
                formatted = clean_content.format(*message_args, **tmp)
            except (ValueError, KeyError, IndexError) as e:
                await self.bot.send_message(
                    ctx.message.channel,
                    ":x: Tag failed to compile -> {}".format(' '.join(e.args))
                )
                return

            # Add the prefix to the string and call `process_commands`.
            prefix = await self.bot.get_command_prefix(ctx.bot, ctx.message)
            final = prefix + formatted

            # Update the message.
            ctx.message.content = final

            await self.bot.process_commands(ctx.message)
            return

        try:
            await self.bot.send_message(ctx.message.channel, content)
        except Exception as e:
            # Panic, and dispatch on_command_error.
            new_e = CommandInvokeError(e)
            new_e.__cause__ = e
            self.bot.dispatch("command_error", new_e, ctx)


def setup(bot):
    bot.add_cog(Tags(bot))
