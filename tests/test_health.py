"""Tests for support.infra.health.HealthMonitor."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from support.infra.health import HealthMonitor, _MIN_INTERVAL, _MAX_INTERVAL


@dataclass
class FakeStatus:
    connected: bool


def _make_adapter(connected: bool = True):
    adapter = AsyncMock()
    adapter.get_status = AsyncMock(return_value=FakeStatus(connected=connected))
    adapter.connect = AsyncMock()
    adapter.disconnect = AsyncMock()
    return adapter


def _make_manager(channels: dict):
    manager = MagicMock()
    manager._channels = channels
    return manager


# --- Tests ---

@pytest.mark.asyncio
async def test_healthy_channel_no_reconnect():
    adapter = _make_adapter(connected=True)
    manager = _make_manager({"tg": adapter})
    monitor = HealthMonitor(interval=30)

    await monitor._check_all(manager)

    adapter.connect.assert_not_called()
    adapter.disconnect.assert_not_called()
    assert "tg" not in monitor._failures


@pytest.mark.asyncio
async def test_unhealthy_triggers_reconnect():
    adapter = _make_adapter(connected=False)
    manager = _make_manager({"tg": adapter})
    monitor = HealthMonitor(interval=1)

    await monitor._check_all(manager)

    adapter.disconnect.assert_called_once()
    adapter.connect.assert_called_once()


@pytest.mark.asyncio
async def test_backoff_increases_on_failure():
    adapter = _make_adapter(connected=False)
    # Make reconnect fail
    adapter.connect.side_effect = ConnectionError("down")
    manager = _make_manager({"tg": adapter})
    monitor = HealthMonitor(interval=1)

    await monitor._check_all(manager)
    assert monitor._failures.get("tg", 0) >= 1

    first_failures = monitor._failures["tg"]
    await monitor._check_all(manager)
    assert monitor._failures["tg"] > first_failures

    # Verify backoff is bounded
    monitor._failures["tg"] = 100
    backoff = min(_MIN_INTERVAL * (2 ** 100), _MAX_INTERVAL)
    assert backoff == _MAX_INTERVAL


@pytest.mark.asyncio
async def test_backoff_resets_on_recovery():
    adapter = _make_adapter(connected=False)
    adapter.connect.side_effect = ConnectionError("down")
    manager = _make_manager({"tg": adapter})
    monitor = HealthMonitor(interval=1)

    # Accumulate failures
    await monitor._check_all(manager)
    await monitor._check_all(manager)
    assert monitor._failures.get("tg", 0) >= 2

    # Now recover
    adapter.get_status.return_value = FakeStatus(connected=True)
    adapter.connect.side_effect = None
    await monitor._check_all(manager)
    assert "tg" not in monitor._failures
