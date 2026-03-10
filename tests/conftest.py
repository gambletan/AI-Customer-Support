"""Common test fixtures."""

from __future__ import annotations

import pytest
import pytest_asyncio

from support.cs_store import CSStore


@pytest_asyncio.fixture()
async def store(tmp_path):
    """Provide an async CSStore backed by a temporary database file."""
    db_path = str(tmp_path / "test.db")
    s = CSStore(db_path)
    await s.connect()
    yield s
    await s.close()
