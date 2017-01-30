"""
Generic tag bot, yay.
"""
import asyncio
import shlex

import traceback
from concurrent.futures import ProcessPoolExecutor

import discord
from discord.ext import commands
from discord.ext.commands import CommandError, CommandNotFound, CommandInvokeError
from jinja2.sandbox import SandboxedEnvironment

from joku.bot import Jokusoramame, Context

# Import a few modules, for usage inside the renderer.
import random
import string
import base64

from joku.cogs._common import Cog
from joku.tagengine import TagEngine


class Tags(Cog):
    def __init__(self, bot: Jokusoramame):
        super().__init__(bot)

        self.engine = TagEngine(self.bot)

    @commands.group(pass_context=True, invoke_without_command=True,
                    aliases=["tags"])
    async def tag(self, ctx, *, name: str):
        """
        Tags are like aliases or autoresponses that can be added to the bot.

        They are made with `tag create`, and deleted with `tag delete`.
        To be accessed, they are simply called like commands are.
        """
        tag_obb = await ctx.bot.rethinkdb.get_tag(ctx.message.server, name)
        if not tag_obb:
            await ctx.channel.send("Tag not found.")
            return

        owner = ctx.bot.get_member(tag_obb["owner_id"])

        em = discord.Embed(title=tag_obb["name"], description=tag_obb["content"])
        em.add_field(name="Owner", value=owner.mention if owner else "<Unknown>")
        em.add_field(name="Last Modified", value=tag_obb["last_modified"].isoformat())

        # Display the tag info.
        await ctx.channel.send(embed=em)

    @tag.command(pass_context=True, aliases=["list"])
    async def all(self, ctx):
        """
        Shows all the tags for the current server
        """
        # looks kinda bleak but i try my best *shrug*
        server_tags = await ctx.bot.rethinkdb.get_all_tags_for_server(ctx.message.server)
        if not server_tags:
            await ctx.channel.send("This server has no tags.")
            return

        await ctx.channel.send(", ".join([x['name'] for x in server_tags]))

    @tag.command(pass_context=True, aliases=["edit"])
    async def create(self, ctx, name: str, *, content: str):
        """
        Creates a new tag.

        This will overwrite other tags with the same name, if you are the owner or an administrator.
        """
        existing_tag = await ctx.bot.rethinkdb.get_tag(ctx.message.server, name)

        if existing_tag:
            # Check for the admin perm.
            if not ctx.message.author.server_permissions.administrator:
                # Check if the owner_id matches the author id.
                if ctx.message.author.id != existing_tag["owner_id"]:
                    await ctx.channel.send(":x: You cannot edit somebody else's tag.")
                    return

            # Don't overwrite the owner_id.
            owner_id = existing_tag["owner_id"]
        else:
            owner_id = ctx.message.author.id

        # Replace stuff in content.
        content = content.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")

        # Set the tag.
        await ctx.bot.rethinkdb.save_tag(ctx.message.server, name, content, {}, owner=owner_id)
        await ctx.channel.send(":heavy_check_mark: Tag **{}** saved.".format(name))

    @tag.command(pass_context=True, aliases=["remove"])
    async def delete(self, ctx, *, name: str):
        """
        Deletes a tag.

        You must be the owner of the tag, or an administrator.
        """
        existing_tag = await ctx.bot.rethinkdb.get_tag(ctx.message.server, name)

        if not existing_tag:
            await ctx.channel.send(":x: This tag does not exist.")
            return

        # Check the owner_id
        if not ctx.message.author.server_permissions.administrator:
            if existing_tag["owner_id"] != ctx.message.author.id:
                await ctx.channel.send(":x: You do not have permission to edit this tag.")
                return

        # Now, delete the tag.
        await ctx.bot.rethinkdb.delete_tag(ctx.message.server, name)
        await ctx.channel.send(":skull_and_crossbones: Tag deleted.")

    @staticmethod
    def _render_template(content: str, params: dict):
        """
        Renders a template inside a the ProcessPoolExecutor.

        :param content: The content of the template to render.
        """
        template_env = SandboxedEnvironment()
        template_env.globals.update({
            "random": random,
            "string": string,
            "base64": base64,
            "list": list,
            "tuple": tuple,
            "dict": dict
        })

        tmpl = template_env.from_string(content)
        return tmpl.render(**params)

    # Unlike other bots, tags are registered like full commands.
    # So, they're entirely handled inside on_command_error.
    # This will catch the CommandNotFound, and try and find the tag.
    async def on_command_error(self, exc: CommandError, ctx: Context):
        if not isinstance(exc, CommandNotFound):
            # We don't want to catch any non-command not found errors.
            return

        # Extract the tag from the message content.
        cmd = ctx.message.content[len(ctx.prefix):]
        cmd = cmd.split(" ")[0]

        # Create the arguments for the template.
        args = {
            "args": shlex.split(ctx.message.content[len(ctx.prefix):]),
            "message": ctx.message,
            "channel": ctx.message.channel,
            "author": ctx.message.author,
            "server": ctx.message.guild
        }

        # Render the template, using the args.
        try:
            coro = self.engine.render_template(cmd, ctx=ctx, **args)
            rendered = await coro
        except (asyncio.CancelledError, asyncio.TimeoutError) as e:
            rendered = "**Timed out waiting for template to render.**"
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__)
            rendered = "**Error when compiling template:**\n`{}`".format(e)
        else:
            if rendered is None:
                # Tag doesn't exist, return.
                return

        try:
            await ctx.message.channel.send(rendered)
        except Exception as e:
            # Panic, and dispatch on_command_error.
            new_e = CommandInvokeError(e)
            new_e.__cause__ = e
            ctx.bot.dispatch("command_error", new_e, ctx)


def setup(bot):
    bot.add_cog(Tags(bot))
