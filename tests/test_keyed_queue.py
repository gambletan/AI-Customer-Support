"""Tests for support.infra.keyed_queue.KeyedAsyncQueue."""

from __future__ import annotations

import asyncio

import pytest

from support.infra.keyed_queue import KeyedAsyncQueue


@pytest.mark.asyncio
async def test_serial_execution_same_key():
    """Tasks under the same key run one at a time (FIFO)."""
    order: list[int] = []

    async def task(n: int, delay: float):
        order.append(n)
        await asyncio.sleep(delay)
        order.append(-n)  # negative marks completion

    q = KeyedAsyncQueue()
    # Launch two tasks on the same key concurrently
    await asyncio.gather(
        q.run("k1", task(1, 0.05)),
        q.run("k1", task(2, 0.01)),
    )
    # Task 1 must fully complete before task 2 starts
    assert order == [1, -1, 2, -2]


@pytest.mark.asyncio
async def test_parallel_execution_different_keys():
    """Tasks on different keys run concurrently."""
    started: list[str] = []

    async def task(key: str):
        started.append(key)
        await asyncio.sleep(0.05)

    q = KeyedAsyncQueue()
    await asyncio.gather(
        q.run("a", task("a")),
        q.run("b", task("b")),
    )
    # Both should have started before either finishes (order may vary)
    assert set(started) == {"a", "b"}


@pytest.mark.asyncio
async def test_error_handling():
    """Exception in a coroutine is caught; subsequent tasks still run."""
    errors: list[tuple[str, BaseException]] = []

    async def on_error(key: str, exc: BaseException):
        errors.append((key, exc))

    q = KeyedAsyncQueue(on_error=on_error)

    async def failing():
        raise ValueError("boom")

    await q.run("k1", failing())
    assert len(errors) == 1
    assert errors[0][0] == "k1"
    assert isinstance(errors[0][1], ValueError)

    # Key should still work after error
    result = []

    async def ok():
        result.append("done")

    await q.run("k1", ok())
    assert result == ["done"]


@pytest.mark.asyncio
async def test_lock_cleanup():
    """Locks are removed after all tasks for a key complete."""
    q = KeyedAsyncQueue()

    async def noop():
        pass

    await q.run("temp", noop())
    # After completion, the key should be cleaned up
    assert "temp" not in q._locks
    assert "temp" not in q._active
