"""
Python documentation functions.
"""
from typing import Dict

from curio.thread import async_thread
from curious.commands import Context, Plugin
from curious.commands.decorators import autoplugin
from logbook import Logger
from sphinx.config import Config
from sphinx.ext import intersphinx
from sphinx.util.tags import Tags

from jokusoramame.bot import Jokusoramame

logger = Logger(__name__)


class MockSphinxApp:
    """
    Mock app used for downloading objects.inv.
    """

    def __init__(self, logger):
        self.logger = logger
        self.config = Config(None, '', {}, Tags())
        self.config.intersphinx_timeout = 5

    def info(self, msg):
        self.logger.info(msg)

    def warn(self, msg):
        self.logger.warn(msg)


@autoplugin
class Pydoc(Plugin):
    """
    Python documentation functions.
    """
    def __init__(self, client: Jokusoramame):
        super().__init__(client)

        self._pydoc_data = {}

    async def load(self):
        return await self.spawn(self._setup_db)

    @async_thread()
    def _setup_db(self):
        """
        Sets up the Pydoc database.
        """
        logger.info("Downloading PyDoc objects.inv information...")
        docs: Dict[str, str] = self.client.config.get("pydocs", {})
        app = MockSphinxApp(logger)
        for name, url in docs.items():
            if not url.endswith("/objects.inv"):
                url = url + "/objects.inv"

            data = intersphinx.fetch_inventory(app, '', url)
            if not data:
                logger.warning(f"Failed to download PyDocs for '{name}'. Skipping.'")
                continue

            # copy data into _pydoc_data
            self._pydoc_data[name] = {}

            for kx, value in data.items():
                # ignore sphinx directives (??)
                if kx.startswith("std"):
                    continue

                for key, subvals in value.items():
                    self._pydoc_data[name][key] = subvals

    @async_thread()
    def command_pydoc(self, ctx: Context, *, search: str):
        """
        Searches the pydoc for the specified term.
        """