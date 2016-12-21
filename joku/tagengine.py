"""
A Jinja2-based tag engine for tags.
"""
import dill
from joku.mp2 import ProcessPoolExecutor

import asyncio
import discord
from jinja2 import Template
from jinja2.sandbox import SandboxedEnvironment

from joku.bot import Jokusoramame, Context

# Template imports.


class TagEngine(object):
    def __init__(self, bot: Jokusoramame):
        # Template environment.
        # This is a SandboxedEnvironment for security purposes.
        self.tmpl_env = SandboxedEnvironment()

        # The ProcessPoolExecutor used.
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
    def _pp_render_template(tmpl_env: SandboxedEnvironment, tag: dict, kwargs=None):
        """
        Called inside the process pool to render the template.
        """
        template = tmpl_env.from_string(tag.get("content", "**Broken tag!**"))  # type: Template

        variables = tag.get("variables", {})

        def _set_variable(name, value):
            variables[name] = value

        local = {
            "set_variable": _set_variable,
            **variables,
        }
        if kwargs:
            local.update(kwargs)

        rendered = template.render(**local)

        return rendered, variables

    async def _render_template(self, tag: dict, **kwargs):
        """
        Renders the template in a process pool.
        """
        coro = self.bot.loop.run_in_executor(self.executor,
                                             self._pp_render_template, self.tmpl_env, tag, kwargs)

        coro = asyncio.wait_for(coro, 5, loop=self.bot.loop)

        rendered, new_variables = await coro

        return rendered, new_variables

    async def render_template(self, tag_id: str, ctx: Context = None, server: discord.Server = None,
                              **kwargs) -> str:
        """
        Renders a template.

        This will load all variables, render the template, and return the rendered template as output.
        """
        server = server or ctx.message.server

        tag = await self.bot.rethinkdb.get_tag(server, tag_id)
        if not tag:
            return None

        final_template, new_variables = await self._render_template(tag, **kwargs)

        await self.bot.rethinkdb.save_tag(server, tag_id, content=tag.get("content"),
                                          variables=new_variables)

        return final_template
