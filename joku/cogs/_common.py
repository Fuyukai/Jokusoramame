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

    def __init__(self, bot: Jokusoramame):
        self.local = threading.local()
        self.local.bot = bot

    @property
    def bot(self) -> 'Jokusoramame':
        """
        :return: The bot instance associated with this thread.
        """
        return self.local.bot

    @classmethod
    def setup(cls, bot: Jokusoramame):
        bot.add_cog(cls(bot))
