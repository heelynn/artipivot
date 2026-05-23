"""PollingChangeNotifier — database-backed polling notification.

Replaces InProcessNotifier as the default. Works with any DocumentStore
that implements insert_notification / query_notifications.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Callable

import structlog

from artipivot.storage.base import ChangeNotifier, DocumentStore

logger = structlog.get_logger(__name__)

_CLEANUP_INTERVAL = 3600  # 1 hour between cleanup runs
_RETENTION_HOURS = 1.0    # Keep notifications for 1 hour


class PollingChangeNotifier(ChangeNotifier):
    """Database-polling change notifier.

    Producers write to a ``notifications`` table via ``insert_notification()``.
    Consumers poll the table at a configurable interval and invoke callbacks
    for new notifications since their last seen timestamp.

    Works with SQLite, PostgreSQL, MySQL, or any DocumentStore with
    ``insert_notification`` / ``query_notifications`` / ``cleanup_notifications``.
    """

    def __init__(
        self,
        store: DocumentStore,
        poll_interval: float | None = None,
    ) -> None:
        self._store = store
        self._poll_interval = poll_interval or float(
            os.environ.get("ARTIPIVOT_NOTIFY_POLL_INTERVAL", "1.0")
        )
        self._subscriptions: dict[str, list[Callable]] = {}
        self._last_seen: dict[str, str] = {}  # collection → ISO timestamp
        self._running = False
        self._tasks: list[asyncio.Task] = []

    # ── ChangeNotifier ABC ──

    async def subscribe(self, collection: str, callback: Callable) -> None:
        """Subscribe to changes in a collection.

        The callback receives (collection, key, action, data).
        Only processes notifications created AFTER subscription.
        """
        if collection not in self._subscriptions:
            self._subscriptions[collection] = []
            self._last_seen[collection] = _utc_now()
            if self._running:
                self._tasks.append(
                    asyncio.create_task(self._poll_loop(collection))
                )
        self._subscriptions[collection].append(callback)
        logger.info(
            "polling_notifier.subscribed",
            collection=collection,
            start_time=self._last_seen[collection],
        )

    async def notify(self, collection: str, key: str, action: str, data: dict) -> None:
        """Insert a notification record for polling consumers."""
        store = self._store
        # Handle both SQLite (sync) and async stores
        fn = getattr(store, "insert_notification", None)
        if fn is None:
            logger.warning(
                "polling_notifier.unsupported_store",
                store_type=type(store).__name__,
            )
            return
        if asyncio.iscoroutinefunction(fn):
            await fn(collection, key, action, data)
        else:
            fn(collection, key, action, data)

    async def start(self) -> None:
        """Start polling loops for all subscribed collections."""
        self._running = True
        for collection in self._subscriptions:
            self._tasks.append(
                asyncio.create_task(self._poll_loop(collection))
            )
        self._tasks.append(
            asyncio.create_task(self._cleanup_loop())
        )
        logger.info("polling_notifier.started", poll_interval=self._poll_interval)

    async def stop(self) -> None:
        """Cancel all polling tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("polling_notifier.stopped")

    # ── Internal ──

    async def _poll_loop(self, collection: str) -> None:
        """Poll for new notifications on a single collection."""
        while self._running:
            try:
                await self._poll_once(collection)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.error(
                    "polling_notifier.poll_error",
                    collection=collection,
                    exc_info=True,
                )
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self, collection: str) -> None:
        """Query and dispatch new notifications for one collection."""
        since = self._last_seen.get(collection, _utc_now())
        store = self._store
        fn = getattr(store, "query_notifications", None)
        if fn is None:
            return

        if asyncio.iscoroutinefunction(fn):
            notifications = await fn(collection, since)
        else:
            notifications = fn(collection, since)

        callbacks = self._subscriptions.get(collection, [])
        for note in notifications:
            for cb in callbacks:
                try:
                    await cb(
                        note["collection"],
                        note["key"],
                        note["action"],
                        note["data"],
                    )
                except Exception:
                    logger.error(
                        "polling_notifier.callback_error",
                        collection=collection,
                        exc_info=True,
                    )
            # Advance last_seen to this notification's timestamp
            note_time = note.get("created_at", since)
            if note_time > since:
                since = note_time

        self._last_seen[collection] = since

    async def _cleanup_loop(self) -> None:
        """Periodically clean up old notifications."""
        while self._running:
            try:
                await asyncio.sleep(_CLEANUP_INTERVAL)
                store = self._store
                fn = getattr(store, "cleanup_notifications", None)
                if fn is not None:
                    if asyncio.iscoroutinefunction(fn):
                        deleted = await fn(_RETENTION_HOURS)
                    else:
                        deleted = fn(_RETENTION_HOURS)
                    if deleted:
                        logger.debug(
                            "polling_notifier.cleaned",
                            deleted=deleted,
                        )
            except asyncio.CancelledError:
                return
            except Exception:
                logger.error(
                    "polling_notifier.cleanup_error",
                    exc_info=True,
                )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
