import curio
import datetime
from curious import Message
from curious.commands import Plugin
from curious.exc import CuriousError
from logbook import Logger

logger = Logger(__name__)


class AutoDelete(Plugin):
    """
    Automatically deletes messages after a while.
    """
    # TODO: Make this configurable
    CHANNEL_ID = 484909286665879553
    EXCLUDED_MESSAGES = [
        484909304692998154,
    ]

    def __init__(self, bot):
        super().__init__(bot)

        self.task: curio.Task = None

    async def load(self):
        if self.task is not None:
            await self.task.cancel()

        self.task = await curio.spawn(self._do_delete())

    async def unload(self):
        await self.task.cancel()

    async def _do_delete(self):
        while True:
            before = (datetime.datetime.utcnow() - datetime.timedelta(weeks=1))
            channel = self.client.find_channel(self.CHANNEL_ID)

            def predicate(m: Message):
                if m.id in self.EXCLUDED_MESSAGES:
                    return False

                if m.created_at < before:
                    return True

                return False

            logger.info("Preparing to auto-purge messages.")
            try:
                await channel.messages.purge(
                    predicate=predicate
                )
            except CuriousError:
                logger.exception("Failed to delete some messages.")
            else:
                logger.info("Done purge, sleeping for 6 hours.")

            try:
                await curio.sleep(60 * 60 * 6)
            except curio.CancelledError:
                return
