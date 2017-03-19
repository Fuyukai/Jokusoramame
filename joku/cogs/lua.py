"""
A lua interpreter cog.
"""
import asyncio
import functools
import pickle

import lupa
# this will error on pycharm, until it generates the right skeleton. Ignroe it.
import os
from lupa import LuaRuntime

from discord.ext import commands

from joku.cogs._common import Cog
from joku.core.bot import Context
from joku.core.checks import is_owner
from joku.core.mp2 import ProcessPoolExecutor

NO_RESULT = type("NO_RESULT", (object,), {})

with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "luasandbox.lua")) as f:
    sandbox_preamble = f.read()


# Useful function stubs
def getter(obj, attr_name):
    raise AttributeError("Python object attribute retrieval is forbidden")


def setter(obj, attr_name, value):
    raise AttributeError("Python object attribute setting is forbidden")


def dictify_table_recursively(t):
    """
    Turns a table into a dict.
    """
    d = {}

    for (k, v) in t.items():
        typ = lupa.lua_type(v)
        print(k, v, typ)
        if lupa.lua_type(v) == "table":
            d[k] = dictify_table_recursively(v)
        else:
            d[k] = str(v)

    return d


def exec_lua(code: str):
    # the attribute_handlers are probably enough to prevent access eval otherwise
    lua = LuaRuntime(register_eval=False,
                     unpack_returned_tuples=True,
                     attribute_handlers=(getter, setter))

    # execute the sandbox preamble
    sandbox = lua.execute(sandbox_preamble)

    # call sandbox.run with `glob.sandbox, code`
    # and unpack the variables
    _ = sandbox.run(code, lua.table_from({}))
    if isinstance(_, bool):
        # idk
        return NO_RESULT

    called, result = _

    if lupa.lua_type(result) == 'table':
        # dictify
        result = dictify_table_recursively(result)

    try:
        pickle.dumps(result)
    except:
        return str(result)

    return result


class Lua(Cog):
    """
    Commands to interpret Lua.
    """

    def __init__(self, bot):
        super().__init__(bot)

        self.lua = LuaRuntime(unpack_returned_tuples=True)

        self.mp_pool = ProcessPoolExecutor(max_workers=4)

    @commands.group(name="lua")
    async def _lua(self, ctx: Context):
        """
        Allows evaluating lua code.
        """

    @_lua.command()
    @commands.check(is_owner)
    async def evalraw(self, ctx: Context, *, code: str):
        """
        Evaluates a lua command in the raw form.
        
        This does not go through the sandbox, and is owner only.
        """
        lua = LuaRuntime(unpack_returned_tuples=True)

        if code.startswith("```"):
            code = code[3:]

        if code.endswith("```"):
            code = code[:-3]

        result = lua.execute(code)

        await ctx.send("```{}```".format(result))

    @_lua.command()
    async def exec(self, ctx: Context, *, code: str):
        """
        Executes some Lua code.
        
        The `return` statement will return a value.
        """
        if code.startswith("```"):
            code = code[3:]

        if code.endswith("```"):
            code = code[:-3]

        async with ctx.channel.typing():
            try:
                fut = self.bot.loop.run_in_executor(self.mp_pool, exec_lua, code)
                result = await asyncio.wait_for(fut, timeout=5.0, loop=self.bot.loop)
            except asyncio.CancelledError:
                final = "Timed out waiting for result."
            except (lupa.LuaSyntaxError, lupa.LuaError) as e:
                final = str(e)
            else:
                if result is NO_RESULT:
                    final = "Code executed, but returned nothing."
                else:
                    final = result

        await ctx.send("```{}```".format(final))


setup = Lua.setup
