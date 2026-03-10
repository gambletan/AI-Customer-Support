"""Gateway startup — main() and main_entry().

Wires up channels (WebChat, WuKongIM, Telegram), message routing,
health monitoring, and the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from unified_channel import ChannelManager
from unified_channel.adapters.telegram import TelegramAdapter
from unified_channel.adapters.webchat import WebChatAdapter
from unified_channel.adapters.wkim_compat import WKIMCompatAdapter
from unified_channel.types import ContentType, UnifiedMessage

from .infra.health import HealthMonitor
from .cs_store import CSStore
from .state import (
    cfg,
    logger,
    msg_queue,
    router,
    session_to_topic,
    topic_to_session,
)
import support.state as _state
from .dashboard.api import register_routes as register_dashboard
from .forwarding import (
    forward_to_telegram,
    forward_to_user,
    handle_callback,
    notify_user_online,
    send_history,
    serve_chat_page,
)


async def main() -> None:
    # Validate configuration early
    errors = cfg.validate()
    if errors:
        for e in errors:
            logger.error(e)
        logger.error("Run 'ai-cs setup' to configure")
        sys.exit(1)

    # Initialize async store
    store = CSStore(cfg.db_path)
    await store.connect()
    _state.store = store  # publish to shared state so other modules see it

    s2t, t2s = await store.load_all_mappings()
    session_to_topic.update(s2t)
    topic_to_session.update(t2s)
    logger.info("loaded %d session-topic mappings from DB", len(s2t))

    manager = ChannelManager()

    webchat = WebChatAdapter(port=cfg.webchat_port)
    wkim = WKIMCompatAdapter(port=cfg.wkim_port)
    telegram = TelegramAdapter(token=cfg.telegram_token)

    manager.add_channel(webchat)
    manager.add_channel(wkim)
    manager.add_channel(telegram)

    # --- Group access control: auto-kick unauthorized members --- (gated)
    if cfg.features.access_control and cfg.allowed_agent_ids:
        from telegram.ext import ChatMemberHandler

        async def _on_chat_member(update, context):
            """Kick users who join the support group but aren't on the allowed list."""
            if not update.chat_member or str(update.chat_member.chat.id) != cfg.support_group_id:
                return
            new = update.chat_member.new_chat_member
            if not new or new.status in ("left", "kicked"):
                return
            user_id = str(new.user.id)
            bot_id = str((await telegram._app.bot.get_me()).id)
            if user_id == bot_id:
                return
            if user_id not in cfg.allowed_agent_ids:
                try:
                    await telegram._app.bot.ban_chat_member(
                        chat_id=int(cfg.support_group_id), user_id=int(user_id),
                    )
                    await telegram._app.bot.unban_chat_member(
                        chat_id=int(cfg.support_group_id), user_id=int(user_id),
                    )
                    logger.warning("kicked unauthorized user %s (%s) from support group",
                                   user_id, new.user.full_name)
                except Exception as e:
                    logger.error("failed to kick user %s: %s", user_id, e)

        telegram._app.add_handler(ChatMemberHandler(_on_chat_member, ChatMemberHandler.CHAT_MEMBER))
        logger.info("group access control enabled: %d allowed agents", len(cfg.allowed_agent_ids))

    @manager.on_message
    async def route(msg: UnifiedMessage) -> None:
        if msg.content.type == ContentType.CALLBACK:
            await handle_callback(manager, msg)
            return

        if msg.channel in ("webchat", "wkim"):
            # Serialize per-customer: use chat_id (session_id) as key
            key = msg.chat_id or "unknown"
            await msg_queue.run(key, forward_to_telegram(manager, msg))
        elif msg.channel == "telegram":
            if msg.chat_id == cfg.support_group_id:
                # Check agent authorization — gated
                if cfg.features.access_control and cfg.allowed_agent_ids and msg.sender.id not in cfg.allowed_agent_ids:
                    logger.warning("ignored message from unauthorized user %s in support group", msg.sender.id)
                    return
                # Serialize per-session: use thread_id -> session_id as key
                key = topic_to_session.get(int(msg.thread_id)) if msg.thread_id else None
                if key:
                    await msg_queue.run(key, forward_to_user(manager, msg))
                else:
                    await forward_to_user(manager, msg)

    # Online/offline + history hooks
    first_message_sent: set[str] = set()
    orig_queue_put = webchat._queue.put

    async def enhanced_put(item: UnifiedMessage):
        await orig_queue_put(item)
        sid = item.chat_id
        if sid and sid not in first_message_sent:
            first_message_sent.add(sid)
            # online_status and history are gated inside their functions
            asyncio.create_task(notify_user_online(manager, sid))
            asyncio.create_task(send_history(manager, sid))

    webchat._queue.put = enhanced_put  # type: ignore

    webchat.add_route("GET", "/chat", serve_chat_page)

    # Mount dashboard API on the webchat HTTP server
    register_dashboard(webchat._app)
    await webchat.connect()

    await wkim.connect()
    await telegram.connect()

    # --- Health monitor: auto-reconnect stale channels ---
    health_monitor = HealthMonitor(interval=cfg.health_interval)
    await health_monitor.start(manager)

    # --- Startup log ---
    logger.info("=" * 60)
    logger.info("Customer Service POC started! (full-featured)")
    logger.info("  Web chat:    http://localhost:%d/chat", cfg.webchat_port)
    logger.info("  Dashboard:   http://localhost:%d/api/sessions", cfg.webchat_port)
    logger.info("  WuKongIM:    http://localhost:%d", cfg.wkim_port)
    logger.info("  Telegram:    group %s", cfg.support_group_id)
    logger.info("  DB:          %s", cfg.db_path)
    logger.info("  Timeout:     %ds", cfg.reply_timeout)
    logger.info("  Health:      every %ds", cfg.health_interval)
    logger.info("  Agents:      %s", cfg.agents or "(auto-assign off)")
    logger.info("  Max/agent:   %d sessions", cfg.max_sessions_per_agent)
    logger.info("  Access:      %s",
                f"{len(cfg.allowed_agent_ids)} allowed agents" if cfg.features.access_control and cfg.allowed_agent_ids
                else "open (anyone in group can reply)")
    logger.info("  Restored:    %d sessions", len(s2t))
    for line in cfg.summary():
        logger.info("  %s", line)
    logger.info("  Model Router:")
    for line in router.summary():
        logger.info("    %s", line)
    logger.info("=" * 60)

    try:
        await asyncio.gather(
            manager._consume(webchat),
            manager._consume(wkim),
            manager._consume(telegram),
        )
    finally:
        await health_monitor.stop()


def main_entry() -> None:
    """Synchronous entry point for the ``ai-cs`` console script."""
    asyncio.run(main())
