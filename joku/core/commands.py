"""
Custom command subclasses because I hate myself
"""
import argparse

from discord.ext.commands import command, Command, CommandError
from discord.ext.commands.errors import UserInputError

DoNotRun = type("DoNotRun", (CommandError,), {})


class ArgparseCommand(Command):
    """
    A command that uses :mod:`argparse` to parse arguments.
    
    This requires a nested class.
    
    >>> class Something(Cog):
    ...     @command(cls=ArgparseCommand)
    ...     class something:
    ...         # must be named `parser`
    ...         parser = argparse.ArgumentParser()
    ...         parser.add_argument("-a", "--append", help="Append something", nargs=1, default="heck")
    ...
    ...         async def invoke(self, ctx: Context, parsed):
    ...             print(parsed.a)
    
    
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not isinstance(self.callback, type):
            raise ValueError("Inner command should be a class")

        if not hasattr(self.callback, "parser"):
            raise ValueError("Nested class must have a `parser` attribute")

        if not hasattr(self.callback, "invoke"):
            raise ValueError("Nested class must have an `invoke` attribute")

        # monkeypatch some stuff
        self.callback.__call__ = self.callback.invoke

        def _error(_, message: str):
            raise UserInputError(message)

        self.callback.parser.error = _error

        # set callback to an instance of itself
        self.callback = self.callback()

    async def _parse_arguments(self, ctx):
        # add instance if applicable
        ctx.args = [] if self.instance is None else [self.instance]
        # always add context
        ctx.args.append(ctx)

        # get the full string to parse
        full = ctx.view.read_rest()
        # pass the string to argparse and get the namespace
        parser = self.callback.parser  # type: argparse.ArgumentParser
        parsed = parser.parse_args(full)

        ctx.args.append(parsed)

