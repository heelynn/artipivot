"""Lazy-initialized async SQLite checkpointer.

Creates the aiosqlite connection on first ``setup()`` call,
so the factory's ``create()`` remains synchronous.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple


class LazyAsyncSqliteCheckpointer(BaseCheckpointSaver):
    """Proxy that defers ``AsyncSqliteSaver`` creation until ``setup()``.

    LangGraph's ``AsyncSqliteSaver`` requires an ``aiosqlite`` connection,
    which must be opened inside an async context. This proxy lets the
    synchronous ``SqliteFactory.create()`` return immediately, then
    initializes the real checkpointer when ``StorageProvider.setup()``
    calls ``await backend.setup()``.
    """

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self._db_path = db_path
        self._conn: Any = None
        self._saver: Any = None

    async def setup(self) -> None:
        """Open the aiosqlite connection and initialize the saver."""
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        if self._saver is not None:
            return

        self._conn = aiosqlite.connect(self._db_path)
        await self._conn.__aenter__()
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        self._saver = AsyncSqliteSaver(self._conn)
        await self._saver.setup()

    def _check(self) -> Any:
        if self._saver is None:
            raise RuntimeError(
                "LazyAsyncSqliteCheckpointer not initialized — call setup() first"
            )
        return self._saver

    # ── Delegate core async methods ──

    async def aget_tuple(self, config) -> CheckpointTuple | None:
        return await self._check().aget_tuple(config)

    async def alist(self, config=None, *, filter=None, before=None, limit=None):
        async for tpl in self._check().alist(config, filter=filter, before=before, limit=limit):
            yield tpl

    async def aput(self, config, checkpoint, metadata, new_versions) -> Any:
        return await self._check().aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path="") -> None:
        return await self._check().aput_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        return await self._check().adelete_thread(thread_id)
