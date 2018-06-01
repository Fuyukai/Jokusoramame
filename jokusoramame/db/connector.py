"""
A custom connector, that wraps asyncpg in curio.
"""
from asyncqlio.backends.postgresql.asyncpg import AsyncpgConnector, AsyncpgResultSet, \
    AsyncpgTransaction
from curio import asyncio_coroutine

from jokusoramame.utils import loop as bridge_loop


def patch(func):
    """
    Patches a function to use the bridge loop.
    """
    return asyncio_coroutine(bridge_loop)(func)


class CurioAsyncpgConnector(AsyncpgConnector):
    """
    A wrapper for an asyncpg connector, using curio.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.params["max_size"] = 50

        # Monkeypatch some methods
        self.close = patch(self.close)
        self.connect = patch(self.connect)

    def get_transaction(self):
        """
        Overridden get_transaction to return a curio-compatible one.
        """
        return CurioAsyncpgTransaction(self)


class CurioAsyncpgTransaction(AsyncpgTransaction):
    """
    A wrapper for an asyncpg transaction, using curio.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Monkeypatch some more
        self.begin = patch(self.begin)
        self.commit = patch(self.commit)
        self.rollback = patch(self.rollback)
        self.close = patch(self.close)
        self.create_savepoint = patch(self.create_savepoint)
        self.release_savepoint = patch(self.release_savepoint)

        # cursor is our own method
        # so we can safely patch it as well as execute
        self.execute = patch(self.execute)
        self.cursor = patch(self.cursor)

    async def cursor(self, sql: str, params=None) -> 'CurioAsyncpgResultSet':
        """
        Overridden cursor to return a curio-compatible result set.
        """
        res = await super().cursor(sql, params)
        return CurioAsyncpgResultSet(cur=res.cur)


class CurioAsyncpgResultSet(AsyncpgResultSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fetch_row = patch(self.fetch_row)
        self.fetch_many = patch(self.fetch_many)
        self.close = patch(self.close)
