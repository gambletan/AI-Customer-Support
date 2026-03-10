"""Gateway startup — main() and main_entry().

Wires up all channels dynamically, message routing,
universal QR code, health monitoring, and the event loop.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sys

from unified_channel import ChannelManager
from unified_channel.adapters.telegram import TelegramAdapter
from unified_channel.adapters.webchat import WebChatAdapter
from unified_channel.adapters.wkim_compat import WKIMCompatAdapter
from unified_channel.types import ContentType, UnifiedMessage

from .channels import (
    CHANNEL_BY_PREFIX,
    CHANNELS,
    ChannelDef,
    create_adapter,
    get_deeplink,
    get_enabled_channels,
)
from .infra.health import HealthMonitor
from .cs_store import CSStore
from .state import (
    cfg,
    dm_sessions,
    logger,
    msg_queue,
    router,
    session_channel,
    session_to_topic,
    topic_to_session,
)
import support.state as _state
from .dashboard.api import register_routes as register_dashboard
from .forwarding import (
    forward_to_telegram,
    forward_to_user,
    handle_callback,
    handle_dm,
    notify_user_online,
    send_history,
    serve_chat_page,
)


# =============================================================================
# Universal QR Code — one QR, all channels
# =============================================================================

def _make_qr_handler(tg_adapter: TelegramAdapter, im_channels: dict[str, object]):
    """Return handler for QR code + channel selection landing page.

    GET /qr              -> QR code image (points to /connect landing page)
    GET /qr?format=png   -> PNG instead of SVG
    GET /connect         -> landing page listing all enabled IM channels
    """
    from aiohttp import web

    async def serve_qr(request: web.Request) -> web.Response:
        try:
            import segno
        except ImportError:
            return web.Response(text="pip install segno", status=503)

        fmt = request.query.get("format", "svg")
        scale = int(request.query.get("scale", "8"))

        # QR points to the /connect landing page
        base_url = os.environ.get("CS_BASE_URL", f"http://localhost:{cfg.webchat_port}")
        url = f"{base_url}/connect"

        qr = segno.make(url)
        buf = io.BytesIO()
        if fmt == "png":
            qr.save(buf, kind="png", scale=scale, border=2)
            content_type = "image/png"
        else:
            qr.save(buf, kind="svg", scale=scale, border=2)
            content_type = "image/svg+xml"
        buf.seek(0)
        return web.Response(body=buf.read(), content_type=content_type)

    async def serve_connect(request: web.Request) -> web.Response:
        """Landing page: user picks their IM channel."""
        # Build channel links
        links: list[dict[str, str]] = []

        # Telegram (always enabled — core channel)
        bot_username = getattr(tg_adapter, "_bot_username", None)
        if bot_username:
            links.append({"name": "Telegram", "url": f"https://t.me/{bot_username}", "icon": "telegram"})

        # WebChat (always available)
        base_url = os.environ.get("CS_BASE_URL", f"http://localhost:{cfg.webchat_port}")
        links.append({"name": "Web Chat", "url": f"{base_url}/chat", "icon": "web"})

        # Dynamic IM channels with deeplinks
        for ch_def, _ in get_enabled_channels():
            dl = get_deeplink(ch_def)
            if dl:
                links.append({"name": ch_def.name, "url": dl, "icon": ch_def.channel_id})

        html = _build_connect_page(links)
        return web.Response(text=html, content_type="text/html")

    return serve_qr, serve_connect


def _build_connect_page(links: list[dict[str, str]]) -> str:
    """Generate the channel selection landing page HTML."""
    # Channel icon colors
    colors = {
        "telegram": "#0088cc", "whatsapp": "#25D366", "line": "#00C300",
        "discord": "#5865F2", "slack": "#4A154B", "wechat": "#07C160",
        "feishu": "#3370FF", "dingtalk": "#0089FF", "msteams": "#6264A7",
        "qq": "#12B7F5", "matrix": "#0DBD8B", "zalo": "#0068FF",
        "imessage": "#34C759", "web": "#666666",
    }

    buttons = ""
    for link in links:
        color = colors.get(link["icon"], "#333333")
        buttons += f'''
        <a href="{link['url']}" class="channel-btn" style="background:{color}" target="_blank">
            {link['name']}
        </a>'''

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contact Support</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: #f5f5f5; display: flex; justify-content: center; align-items: center;
       min-height: 100vh; padding: 20px; }}
.container {{ background: white; border-radius: 16px; padding: 40px; max-width: 400px;
              width: 100%; box-shadow: 0 4px 20px rgba(0,0,0,0.1); text-align: center; }}
h1 {{ font-size: 24px; margin-bottom: 8px; }}
p {{ color: #666; margin-bottom: 24px; }}
.channels {{ display: flex; flex-direction: column; gap: 12px; }}
.channel-btn {{ display: block; padding: 14px 20px; border-radius: 10px; color: white;
                text-decoration: none; font-size: 16px; font-weight: 500;
                transition: opacity 0.2s; }}
.channel-btn:hover {{ opacity: 0.85; }}
</style>
</head>
<body>
<div class="container">
    <h1>Contact Support</h1>
    <p>Choose your preferred channel</p>
    <div class="channels">{buttons}
    </div>
</div>
</body>
</html>"""


# =============================================================================
# Main
# =============================================================================

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
    _state.store = store

    s2t, t2s = await store.load_all_mappings()
    session_to_topic.update(s2t)
    topic_to_session.update(t2s)

    # Restore DM sessions from all known channel prefixes
    dm_count = 0
    for sid in s2t:
        for ch_def in CHANNELS:
            prefix = f"{ch_def.prefix}_"
            if sid.startswith(prefix):
                dm_sessions.add(sid)
                session_channel[sid] = ch_def.channel_id
                dm_count += 1
                break
    logger.info("loaded %d session-topic mappings from DB (%d DM)", len(s2t), dm_count)

    manager = ChannelManager()

    # --- Core channels (always on) ---
    webchat = WebChatAdapter(port=cfg.webchat_port)
    wkim = WKIMCompatAdapter(port=cfg.wkim_port)
    telegram = TelegramAdapter(token=cfg.telegram_token)

    manager.add_channel(webchat)
    manager.add_channel(wkim)
    manager.add_channel(telegram)

    # --- Dynamic IM channels (auto-detected from env) ---
    im_channels: dict[str, object] = {}
    enabled = get_enabled_channels()
    for ch_def, env_vals in enabled:
        try:
            adapter = create_adapter(ch_def, env_vals)
            manager.add_channel(adapter)
            im_channels[ch_def.channel_id] = adapter
            logger.info("channel enabled: %s (%s)", ch_def.name, ch_def.channel_id)
        except Exception as e:
            logger.error("failed to create %s adapter: %s", ch_def.name, e)

    # --- Group access control: auto-kick unauthorized members ---
    if cfg.features.access_control and cfg.allowed_agent_ids:
        from telegram.ext import ChatMemberHandler

        async def _on_chat_member(update, context):
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
            key = msg.chat_id or "unknown"
            await msg_queue.run(key, forward_to_telegram(manager, msg))
        elif msg.channel == "telegram":
            if msg.chat_id == cfg.support_group_id:
                # Agent message in support group
                if cfg.features.access_control and cfg.allowed_agent_ids and msg.sender.id not in cfg.allowed_agent_ids:
                    logger.warning("ignored message from unauthorized user %s in support group", msg.sender.id)
                    return
                key = topic_to_session.get(int(msg.thread_id)) if msg.thread_id else None
                if key:
                    await msg_queue.run(key, forward_to_user(manager, msg))
                else:
                    await forward_to_user(manager, msg)
            else:
                # Telegram private chat (DM)
                await handle_dm(manager, msg, "tg", "telegram")
        elif msg.channel in im_channels:
            # Any dynamic IM channel (WhatsApp, LINE, Discord, etc.)
            ch_def = next((c for c in CHANNELS if c.channel_id == msg.channel), None)
            if ch_def:
                await handle_dm(manager, msg, ch_def.prefix, ch_def.channel_id)

    # Online/offline + history hooks
    first_message_sent: set[str] = set()
    orig_queue_put = webchat._queue.put

    async def enhanced_put(item: UnifiedMessage):
        await orig_queue_put(item)
        sid = item.chat_id
        if sid and sid not in first_message_sent:
            first_message_sent.add(sid)
            asyncio.create_task(notify_user_online(manager, sid))
            asyncio.create_task(send_history(manager, sid))

    webchat._queue.put = enhanced_put  # type: ignore

    webchat.add_route("GET", "/chat", serve_chat_page)

    # Universal QR + connect landing page
    serve_qr, serve_connect = _make_qr_handler(telegram, im_channels)
    webchat.add_route("GET", "/qr", serve_qr)
    webchat.add_route("GET", "/connect", serve_connect)

    # Mount dashboard API
    register_dashboard(webchat._app)
    await webchat.connect()

    await wkim.connect()
    await telegram.connect()

    # Connect all dynamic IM channels
    for ch_id, adapter in im_channels.items():
        try:
            await adapter.connect()
        except Exception as e:
            logger.error("failed to connect %s: %s", ch_id, e)

    # --- Health monitor ---
    health_monitor = HealthMonitor(interval=cfg.health_interval)
    await health_monitor.start(manager)

    # --- Startup log ---
    consumers = [
        manager._consume(webchat),
        manager._consume(wkim),
        manager._consume(telegram),
    ]
    for adapter in im_channels.values():
        consumers.append(manager._consume(adapter))

    logger.info("=" * 60)
    logger.info("Customer Service started!")
    logger.info("  Web chat:    http://localhost:%d/chat", cfg.webchat_port)
    logger.info("  Dashboard:   http://localhost:%d/api/sessions", cfg.webchat_port)
    logger.info("  Connect:     http://localhost:%d/connect", cfg.webchat_port)
    logger.info("  QR code:     http://localhost:%d/qr", cfg.webchat_port)
    logger.info("  WuKongIM:    http://localhost:%d", cfg.wkim_port)
    logger.info("  Telegram:    group %s", cfg.support_group_id)
    for ch_def, _ in enabled:
        port_str = f" (port {ch_def.default_port})" if ch_def.default_port else ""
        logger.info("  %s:%s%s", ch_def.name, " " * (11 - len(ch_def.name)), port_str)
    logger.info("  DB:          %s", cfg.db_path)
    logger.info("  Timeout:     %ds", cfg.reply_timeout)
    logger.info("  Health:      every %ds", cfg.health_interval)
    logger.info("  Agents:      %s", cfg.agents or "(auto-assign off)")
    logger.info("  Max/agent:   %d sessions", cfg.max_sessions_per_agent)
    logger.info("  Access:      %s",
                f"{len(cfg.allowed_agent_ids)} allowed agents" if cfg.features.access_control and cfg.allowed_agent_ids
                else "open (anyone in group can reply)")
    logger.info("  Channels:    %d enabled (%s)",
                len(enabled), ", ".join(ch.name for ch, _ in enabled))
    logger.info("  Restored:    %d sessions (%d DM)", len(s2t), dm_count)
    for line in cfg.summary():
        logger.info("  %s", line)
    logger.info("  Model Router:")
    for line in router.summary():
        logger.info("    %s", line)
    logger.info("=" * 60)

    try:
        await asyncio.gather(*consumers)
    finally:
        await health_monitor.stop()


def main_entry() -> None:
    """Synchronous entry point for the ``ai-cs`` console script."""
    asyncio.run(main())
