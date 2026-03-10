"""Tests for support.cs_store.CSStore (async aiosqlite version)."""

from __future__ import annotations

from datetime import datetime

import pytest

from support.cs_store import CSStore


# --- Session management ---

@pytest.mark.asyncio
async def test_create_and_get_session(store: CSStore):
    sess = await store.create_session("s1", topic_id=100, channel="webchat", user_name="Alice")
    assert sess["session_id"] == "s1"
    assert sess["topic_id"] == 100
    assert sess["user_name"] == "Alice"
    assert sess["status"] == "active"

    fetched = await store.get_session("s1")
    assert fetched is not None
    assert fetched["session_id"] == "s1"


@pytest.mark.asyncio
async def test_get_session_missing(store: CSStore):
    assert await store.get_session("nonexistent") is None


@pytest.mark.asyncio
async def test_get_session_by_topic(store: CSStore):
    await store.create_session("s1", topic_id=200)
    result = await store.get_session_by_topic(200)
    assert result is not None
    assert result["session_id"] == "s1"
    assert await store.get_session_by_topic(999) is None


@pytest.mark.asyncio
async def test_get_session_by_user_id(store: CSStore):
    await store.create_session("s1", user_id="u1", user_type="member")
    result = await store.get_session_by_user_id("u1")
    assert result is not None
    assert result["session_id"] == "s1"

    # Closed sessions should not be returned
    await store.close_session("s1")
    assert await store.get_session_by_user_id("u1") is None


@pytest.mark.asyncio
async def test_set_topic_id(store: CSStore):
    await store.create_session("s1")
    await store.set_topic_id("s1", 777)
    sess = await store.get_session("s1")
    assert sess["topic_id"] == 777


@pytest.mark.asyncio
async def test_set_assigned_agent(store: CSStore):
    await store.create_session("s1")
    await store.set_assigned_agent("s1", "agent_bob")
    assert await store.get_assigned_agent("s1") == "agent_bob"


@pytest.mark.asyncio
async def test_set_and_get_user_lang(store: CSStore):
    await store.create_session("s1")
    assert await store.get_user_lang("s1") == "zh"  # default
    await store.set_user_lang("s1", "en")
    assert await store.get_user_lang("s1") == "en"


@pytest.mark.asyncio
async def test_get_user_lang_missing_session(store: CSStore):
    assert await store.get_user_lang("nonexistent") == "zh"


@pytest.mark.asyncio
async def test_close_session(store: CSStore):
    await store.create_session("s1")
    await store.close_session("s1")
    sess = await store.get_session("s1")
    assert sess["status"] == "closed"
    assert sess["closed_at"] is not None


@pytest.mark.asyncio
async def test_get_active_sessions(store: CSStore):
    await store.create_session("s1")
    await store.create_session("s2")
    await store.create_session("s3")
    await store.close_session("s2")
    active = await store.get_active_sessions()
    ids = {s["session_id"] for s in active}
    assert ids == {"s1", "s3"}


# --- Topic mapping ---

@pytest.mark.asyncio
async def test_load_all_mappings(store: CSStore):
    await store.create_session("s1", topic_id=10)
    await store.create_session("s2", topic_id=20)
    await store.create_session("s3")  # no topic
    s2t, t2s = await store.load_all_mappings()
    assert s2t == {"s1": 10, "s2": 20}
    assert t2s == {10: "s1", 20: "s2"}


# --- Messages ---

@pytest.mark.asyncio
async def test_add_and_get_messages(store: CSStore):
    await store.create_session("s1")
    id1 = await store.add_message("s1", "user", "hello")
    id2 = await store.add_message("s1", "agent", "hi there")
    id3 = await store.add_message("s1", "user", "thanks")

    msgs = await store.get_messages("s1")
    assert len(msgs) == 3
    assert msgs[0]["content"] == "hello"
    assert msgs[2]["content"] == "thanks"

    # with limit
    msgs = await store.get_messages("s1", limit=2)
    assert len(msgs) == 2
    # should be the last 2 messages (ordered ASC after reversal)
    assert msgs[0]["content"] == "hi there"
    assert msgs[1]["content"] == "thanks"

    # with before_id
    msgs = await store.get_messages("s1", before_id=id3)
    assert len(msgs) == 2
    assert all(m["id"] < id3 for m in msgs)


# --- Unseen messages ---

@pytest.mark.asyncio
async def test_set_last_seen_and_get_unseen(store: CSStore):
    await store.create_session("s1")
    id1 = await store.add_message("s1", "user", "msg1")
    id2 = await store.add_message("s1", "agent", "msg2")
    id3 = await store.add_message("s1", "user", "msg3")

    # Before setting last_seen, all are unseen
    unseen = await store.get_unseen_messages("s1")
    assert len(unseen) == 3

    await store.set_last_seen("s1", id2)
    unseen = await store.get_unseen_messages("s1")
    assert len(unseen) == 1
    assert unseen[0]["id"] == id3


# --- Ratings ---

@pytest.mark.asyncio
async def test_add_and_get_rating(store: CSStore):
    await store.create_session("s1")
    await store.add_rating("s1", 5, "great service")
    rating = await store.get_rating("s1")
    assert rating is not None
    assert rating["score"] == 5
    assert rating["comment"] == "great service"


@pytest.mark.asyncio
async def test_get_rating_missing(store: CSStore):
    await store.create_session("s1")
    assert await store.get_rating("s1") is None


# --- Agent load ---

@pytest.mark.asyncio
async def test_get_agent_load(store: CSStore):
    await store.create_session("s1")
    await store.create_session("s2")
    await store.create_session("s3")
    await store.set_assigned_agent("s1", "alice")
    await store.set_assigned_agent("s2", "alice")
    await store.set_assigned_agent("s3", "bob")

    load = await store.get_agent_load()
    assert load["alice"] == 2
    assert load["bob"] == 1


# --- Tickets ---

@pytest.mark.asyncio
async def test_create_and_get_tickets(store: CSStore):
    await store.create_session("s1")
    tid = await store.create_ticket("s1", "Cannot login", created_by="agent_bob")
    assert isinstance(tid, int)

    tickets = await store.get_tickets("s1")
    assert len(tickets) == 1
    assert tickets[0]["title"] == "Cannot login"
    assert tickets[0]["created_by"] == "agent_bob"
    assert tickets[0]["status"] == "open"


# --- Sensitive log ---

@pytest.mark.asyncio
async def test_log_sensitive(store: CSStore):
    await store.create_session("s1")
    await store.log_sensitive("s1", "my password is 1234", ["password", "1234"])
    # Just verify it doesn't raise; the table is write-only in the public API


# --- Reports ---

@pytest.mark.asyncio
async def test_daily_report(store: CSStore):
    # SQLite datetime('now') uses UTC
    from datetime import timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await store.create_session("s1")
    await store.create_session("s2")
    await store.add_message("s1", "user", "hi")
    await store.add_message("s1", "agent", "hello")
    await store.add_rating("s1", 4)
    await store.close_session("s2")

    report = await store.daily_report(today)
    assert report["date"] == today
    assert report["total_sessions"] == 2
    assert report["closed_sessions"] == 1
    assert report["total_messages"] == 2
    assert report["avg_rating"] == 4.0


# --- Hot keywords ---

@pytest.mark.asyncio
async def test_hot_keywords(store: CSStore):
    await store.create_session("s1")
    await store.add_message("s1", "user", "refund please refund")
    await store.add_message("s1", "user", "I want refund now")
    await store.add_message("s1", "agent", "let me check")  # agent msg, ignored

    keywords = await store.hot_keywords(days=7, top_n=5)
    assert isinstance(keywords, list)
    # "refund" should appear among top keywords
    words = [w for w, _ in keywords]
    assert "refund" in words
