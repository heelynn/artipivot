"""Shared test fixtures."""

from __future__ import annotations

import asyncio

import pytest

from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier


@pytest.fixture
def store():
    return InMemoryDocumentStore()


@pytest.fixture
def notifier():
    return InProcessNotifier()
