from collections import OrderedDict

import threading

from joku.bot import Jokusoramame


class _CogMeta(type):
    def __prepare__(*args, **kwargs):
        # Use an OrderedDict for the class body.
        return OrderedDict()


class Cog(metaclass=_CogMeta):
    def __init__(self, bot: Jokusoramame):
        self._bot = bot

        self.logger = self.bot.logger

    @property
    def bot(self) -> 'Jokusoramame':
        """
        :return: The bot instance associated with this cog.
        """
        return self._bot

    @classmethod
    def setup(cls, bot: Jokusoramame):
        bot.add_cog(cls(bot))