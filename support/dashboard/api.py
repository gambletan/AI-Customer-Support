"""Dashboard REST API — lightweight aiohttp routes.

Endpoints:
    GET  /api/sessions          — active sessions list
    GET  /api/sessions/:id      — single session detail + recent messages
    GET  /api/report            — daily report (optional ?date=YYYY-MM-DD)
    GET  /api/hotwords          — hot keywords (optional ?days=7&top=20)
    GET  /api/agents/load       — per-agent active session count
    GET  /api/queue             — current waiting queue
"""

from __future__ import annotations

from aiohttp import web

import support.state as _state


def _store():
    """Late-bind store access (store is initialized after import)."""
    assert _state.store is not None, "store not initialized"
    return _state.store


def register_routes(app: web.Application) -> None:
    """Register all dashboard API routes on the given aiohttp app."""
    app.router.add_get("/api/sessions", handle_sessions)
    app.router.add_get("/api/sessions/{session_id}", handle_session_detail)
    app.router.add_get("/api/report", handle_report)
    app.router.add_get("/api/hotwords", handle_hotwords)
    app.router.add_get("/api/agents/load", handle_agent_load)
    app.router.add_get("/api/queue", handle_queue)


def _json(data: object, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


async def handle_sessions(request: web.Request) -> web.Response:
    sessions = await _store().get_active_sessions()
    for s in sessions:
        s["has_topic"] = s["session_id"] in _state.session_to_topic
    return _json({"sessions": sessions, "count": len(sessions)})


async def handle_session_detail(request: web.Request) -> web.Response:
    session_id = request.match_info["session_id"]
    session = await _store().get_session(session_id)
    if not session:
        return _json({"error": "session not found"}, status=404)

    limit = int(request.query.get("limit", "50"))
    messages = await _store().get_messages(session_id, limit=limit)
    rating = await _store().get_rating(session_id)
    tickets = await _store().get_tickets(session_id)

    return _json({
        "session": session,
        "messages": messages,
        "rating": rating,
        "tickets": tickets,
    })


async def handle_report(request: web.Request) -> web.Response:
    date = request.query.get("date")
    report = await _store().daily_report(date)
    return _json(report)


async def handle_hotwords(request: web.Request) -> web.Response:
    days = int(request.query.get("days", "7"))
    top = int(request.query.get("top", "20"))
    keywords = await _store().hot_keywords(days=days, top_n=top)
    return _json({"days": days, "keywords": [{"word": w, "count": c} for w, c in keywords]})


async def handle_agent_load(request: web.Request) -> web.Response:
    load = await _store().get_agent_load()
    return _json({
        "agents": [{"name": name, "active_sessions": count} for name, count in load.items()],
        "configured_agents": _state.cfg.agents,
        "max_per_agent": _state.cfg.max_sessions_per_agent,
    })


async def handle_queue(request: web.Request) -> web.Response:
    queue_info = []
    for sid in _state.waiting_queue:
        session = await _store().get_session(sid)
        queue_info.append({
            "session_id": sid,
            "user_name": session.get("user_name") if session else None,
            "user_id": session.get("user_id") if session else None,
            "created_at": session.get("created_at") if session else None,
        })
    return _json({"queue": queue_info, "count": len(queue_info)})
