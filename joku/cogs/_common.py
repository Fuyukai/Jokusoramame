from collections import OrderedDict

import threading

from joku.bot import Jokusoramame


class _CogMeta(type):
    def __prepare__(*args, **kwargs):
        # Use an OrderedDict for the class body.
        return OrderedDict()


class Cog(metaclass=_CogMeta):
    """
    A common class for all cogs. This makes the class body ordered, and provides a `local` which stores thread-local
    data. This makes the cogs semi thread-safe.
    """

    class local(threading.local):
        bot = None

    def __init__(self, bot: Jokusoramame):
        self.local.bot = bot

    def __setattr__(self, key, value):
        if hasattr(self, key):
            super().__setattr__(key, value)
        else:
            # Set it on the thread-local object instead.
            setattr(self.local, key, value)

    def __getattribute__(self, item):
        # Get the local.
        local = super().__getattribute__("local")
        if hasattr(local, item):
            return getattr(local, item)

        return super().__getattribute__(item)

    @property
    def bot(self) -> 'Jokusoramame':
        """
        :return: The bot instance associated with this thread.
        """
        return self.local.bot
