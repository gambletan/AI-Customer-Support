"""Tests for dashboard REST API endpoints."""

from __future__ import annotations

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from support.cs_store import CSStore
from support.dashboard.api import register_routes
import support.state as _state


@pytest_asyncio.fixture()
async def api_store(tmp_path):
    db = CSStore(str(tmp_path / "test_api.db"))
    await db.connect()
    old = _state.store
    _state.store = db
    yield db
    _state.store = old
    await db.close()


@pytest_asyncio.fixture()
async def client(api_store):
    app = web.Application()
    register_routes(app)
    server = TestServer(app)
    async with TestClient(server) as c:
        yield c


@pytest.mark.asyncio
async def test_sessions_empty(client):
    resp = await client.get("/api/sessions")
    assert resp.status == 200
    data = await resp.json()
    assert data["count"] == 0
    assert data["sessions"] == []


@pytest.mark.asyncio
async def test_sessions_with_data(client, api_store):
    await api_store.create_session("sess-1", channel="webchat", user_name="Alice")
    await api_store.create_session("sess-2", channel="webchat", user_name="Bob")
    resp = await client.get("/api/sessions")
    data = await resp.json()
    assert data["count"] == 2


@pytest.mark.asyncio
async def test_session_detail(client, api_store):
    await api_store.create_session("sess-1", channel="webchat", user_name="Alice")
    await api_store.add_message("sess-1", "user", "hello")
    await api_store.add_message("sess-1", "agent", "hi there")

    resp = await client.get("/api/sessions/sess-1")
    assert resp.status == 200
    data = await resp.json()
    assert data["session"]["user_name"] == "Alice"
    assert len(data["messages"]) == 2


@pytest.mark.asyncio
async def test_session_detail_not_found(client, api_store):
    resp = await client.get("/api/sessions/nonexistent")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_report(client, api_store):
    resp = await client.get("/api/report")
    assert resp.status == 200
    data = await resp.json()
    assert "total_sessions" in data
    assert "date" in data


@pytest.mark.asyncio
async def test_hotwords(client, api_store):
    await api_store.create_session("sess-1", channel="webchat")
    await api_store.add_message("sess-1", "user", "退货退款怎么办")
    await api_store.add_message("sess-1", "user", "退货流程是什么")

    resp = await client.get("/api/hotwords?days=7&top=10")
    assert resp.status == 200
    data = await resp.json()
    assert "keywords" in data


@pytest.mark.asyncio
async def test_agent_load(client, api_store):
    resp = await client.get("/api/agents/load")
    assert resp.status == 200
    data = await resp.json()
    assert "agents" in data
    assert "max_per_agent" in data


@pytest.mark.asyncio
async def test_queue_empty(client, api_store):
    _state.waiting_queue.clear()
    resp = await client.get("/api/queue")
    assert resp.status == 200
    data = await resp.json()
    assert data["count"] == 0
