"""
A Jinja2-based tag engine for tags.
"""
import asyncio
import inspect
import random
import string
from concurrent.futures import ThreadPoolExecutor

import discord
import functools

import lupa
from discord.abc import GuildChannel
from jinja2 import Template
from jinja2.sandbox import SandboxedEnvironment
from lupa._lupa import LuaRuntime

from joku.cogs.lua import sandbox_preamble, dictify_table_recursively, NO_RESULT
from joku.core.bot import Context, Jokusoramame
from joku.core.mp2 import ProcessPoolExecutor
from joku.db.tables import Tag


class TagEngine(object):
    def __init__(self, bot: Jokusoramame):
        # Template environment.
        # This is a SandboxedEnvironment for security purposes.
        self.tmpl_env = SandboxedEnvironment()

        # The process pool used.
        self.executor = ProcessPoolExecutor()

        # The bot instance.
        # We use this for getting the tag instance.
        self.bot = bot

        # Update the globals of the template environment.
        self.tmpl_env.globals.update(
            {
                "random": random,
                "string": string,
                "list": list,
                "str": str,
                "tuple": tuple,
            }
        )

    @staticmethod
    def _lua_render_template(luastr: str, kwargs=None):
        """
        Renders a Lua template.
        """

        def getter(obj, attr_name):
            if attr_name.startswith("_"):
                raise AttributeError("Not allowed to access attribute `{}` of `{}`"
                                     .format(attr_name, type(obj).__name__))

            return attr_name

        def setter(obj, attr_name, value):
            raise AttributeError("Python object attribute setting is forbidden")

        # the attribute_handlers are probably enough to prevent access eval otherwise
        lua = LuaRuntime(register_eval=False,
                         unpack_returned_tuples=True,
                         attribute_handlers=(getter, setter))

        # execute the sandbox preamble
        sandbox = lua.execute(sandbox_preamble)

        # call sandbox.run with `glob.sandbox, code`
        # and unpack the variables
        new = {}
        # HECK
        for key, val in kwargs.items():
            new[key] = lua.table_from(val)

        _ = sandbox.run(luastr, lua.table_from(new))
        if isinstance(_, bool):
            # idk
            return NO_RESULT

        called, result = _

        if lupa.lua_type(result) == 'table':
            # dictify
            result = dictify_table_recursively(result)

        return str(result)

    @staticmethod
    def _pp_render_template(tmpl_env: SandboxedEnvironment, tag: Tag, kwargs=None):
        """
        Called inside the process pool to render the template.
        """
        template = tmpl_env.from_string(tag.content or "Broken tag!")  # type: Template

        # variables = tag.get("variables", {})

        # def _set_variable(name, value):
        #     variables[name] = value

        # local = {
        #     "set_variable": _set_variable,
        #     **variables,
        # }
        # if kwargs:
        #     local.update(kwargs)

        rendered = template.render(**kwargs)

        return rendered

    async def _render_template(self, tag: Tag, **kwargs):
        """
        Renders the template in a process pool.
        """
        if tag.lua:
            partial = functools.partial(self._lua_render_template, tag.content, kwargs)
        else:
            partial = functools.partial(self._pp_render_template, self.tmpl_env, tag, kwargs)

        rendered = await asyncio.wait_for(self.bot.loop.run_in_executor(self.executor, partial), 5, loop=self.bot.loop)

        return rendered

    async def render_template(self, tag_id: str, ctx: Context = None, guild: discord.Guild = None,
                              **kwargs) -> str:
        """
        Renders a template.

        This will load all variables, render the template, and return the rendered template as output.
        """
        guild = guild or ctx.message.guild

        tag = await self.bot.database.get_tag(guild, tag_id)
        if not tag:
            return None

        final_template = await self._render_template(tag, **kwargs)

        # await self.bot.database.save_tag(guild, tag_id, content=tag.get("content"),
        #                                  variables=new_variables)

        return final_template
