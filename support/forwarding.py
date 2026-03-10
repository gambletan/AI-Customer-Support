"""Message forwarding: User <-> Telegram support group.

Handles:
- forward_to_telegram: user messages -> agent topic threads
- forward_to_user: agent replies -> user channels
- Topic management, AI auto-reply, sensitive word filtering
- Online/offline notifications, history delivery
- Callback handling (ratings)
"""

from __future__ import annotations

import asyncio
import base64
import io
from datetime import datetime
from pathlib import Path

import httpx
from aiohttp import web
from unified_channel import ChannelManager
from unified_channel.adapters.telegram import TelegramAdapter
from unified_channel.types import (
    Button,
    ContentType,
    OutboundMessage,
    UnifiedMessage,
)

from .state import (
    FAQ,
    SENSITIVE_WORDS,
    cfg,
    dm_sessions,
    logger,
    pending_replies,
    router,
    session_channel,
    session_to_topic,
    store,
    topic_to_session,
    waiting_queue,
)
from .translation import detect_language, translate_text


# =============================================================================
# Voice-to-Text (OpenAI Whisper)
# =============================================================================

async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> str | None:
    """Transcribe audio via OpenAI Whisper API.

    Returns the transcribed text, or None if no API key or on failure.
    """
    if not cfg.openai_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {cfg.openai_api_key}"},
                files={"file": (filename, audio_bytes)},
                data={"model": "whisper-1"},
            )
            resp.raise_for_status()
            result = resp.json()
            text = result.get("text", "").strip()
            return text if text else None
    except Exception as e:
        logger.warning("whisper transcription failed: %s", e)
        return None


def _telegram_file_url(file_path: str) -> str:
    """Build the full Telegram file download URL from a relative file_path."""
    return f"https://api.telegram.org/file/bot{cfg.telegram_token}/{file_path}"


# =============================================================================
# Sensitive Word Filter
# =============================================================================

def check_sensitive(text: str) -> list[str]:
    """Check text for sensitive words. Returns list of matched words."""
    if not SENSITIVE_WORDS:
        return []
    matched = [w for w in SENSITIVE_WORDS if w in text]
    return matched


# =============================================================================
# Topic Management
# =============================================================================

async def get_or_create_topic(
    manager: ChannelManager, session_id: str, user_info: dict, channel: str
) -> int:
    if session_id in session_to_topic:
        return session_to_topic[session_id]

    db_session = await store.get_session(session_id)
    if db_session and db_session.get("topic_id"):
        topic_id = db_session["topic_id"]
        session_to_topic[session_id] = topic_id
        topic_to_session[topic_id] = session_id
        return topic_id

    user_id = user_info.get("user_id")
    if user_id:
        existing = await store.get_session_by_user_id(user_id)
        if existing and existing.get("topic_id"):
            topic_id = existing["topic_id"]
            session_to_topic[session_id] = topic_id
            topic_to_session[topic_id] = session_id
            await store.set_topic_id(session_id, topic_id)
            return topic_id

    tg = manager._channels["telegram"]
    assert isinstance(tg, TelegramAdapter) and tg._app

    user_type = user_info.get("user_type", "anonymous")
    is_auth = user_type == "authenticated"
    name = user_info.get("name")

    topic_name = f"\U0001f464 {name or user_id}" if is_auth else f"\U0001f4ac \u8bbf\u5ba2_{session_id[:6]}"

    topic = await tg._app.bot.create_forum_topic(
        chat_id=int(cfg.support_group_id),
        name=topic_name,
    )
    topic_id = topic.message_thread_id

    session_to_topic[session_id] = topic_id
    topic_to_session[topic_id] = session_id
    session_channel[session_id] = channel

    await store.create_session(
        session_id, topic_id=topic_id, channel=channel,
        user_type=user_type, user_id=user_id,
        user_name=name, user_phone=user_info.get("phone"),
    )

    # Agent assignment (gated)
    assigned = None
    if cfg.features.agent_assignment:
        assigned = await auto_assign_agent(session_id)

    lines = [f"{'👤 登录用户' if is_auth else '💬 匿名访客'}"]
    lines.append(f"• 会话ID: `{session_id}`")
    lines.append(f"• 来源: {channel}")
    if is_auth:
        lines.append(f"• 客户ID: `{user_id}`")
        if name:
            lines.append(f"• 姓名: {name}")
        phone = user_info.get("phone")
        if phone:
            lines.append(f"• 手机: {phone}")
        lines.append(f"\n📋 `/erp {user_id}` | `/order {user_id}`")
    if assigned:
        lines.append(f"• 分配客服: {assigned}")
    lines.append(f"• 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"\n直接回复即可。输入 /help 查看所有命令。")

    await tg._app.bot.send_message(
        chat_id=int(cfg.support_group_id),
        message_thread_id=topic_id,
        text="\n".join(lines),
        parse_mode="Markdown",
    )

    logger.info("created topic %d for session %s (type=%s)", topic_id, session_id, user_type)
    return topic_id


# =============================================================================
# Agent Assignment
# =============================================================================

async def auto_assign_agent(session_id: str) -> str | None:
    """Assign the least-loaded agent. Returns None if no agents or all are at capacity."""
    if not cfg.agents:
        return None
    load = await store.get_agent_load()
    agent = min(cfg.agents, key=lambda a: load.get(a, 0))
    if load.get(agent, 0) >= cfg.max_sessions_per_agent:
        return None  # all agents at capacity
    await store.set_assigned_agent(session_id, agent)
    return agent


async def _dequeue_next(manager: ChannelManager) -> None:
    """Try to assign the next queued customer to a free agent."""
    if not waiting_queue:
        return

    next_sid = waiting_queue[0]
    assigned = await auto_assign_agent(next_sid)
    if not assigned:
        return  # still no capacity

    waiting_queue.pop(0)

    tg = manager._channels["telegram"]
    assert isinstance(tg, TelegramAdapter) and tg._app

    topic_id = session_to_topic.get(next_sid)
    if topic_id:
        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id),
            message_thread_id=topic_id,
            text=f"📥 排队用户已分配给客服 {assigned}，请及时处理。",
        )

    user_ch = _find_user_channel(manager, next_sid)
    if user_ch:
        await user_ch.send(OutboundMessage(
            chat_id=next_sid,
            text="客服已接入，请描述您的问题。",
        ))

    logger.info("dequeued session %s -> agent %s (remaining: %d)", next_sid, assigned, len(waiting_queue))


# =============================================================================
# AI Auto-Reply
# =============================================================================

async def try_ai_reply(text: str) -> str | None:
    """Try AI auto-reply. Uses FAQ keyword match first, then LLM if available."""
    # FAQ keyword match (fast path)
    text_lower = text.strip().lower()
    for keyword, answer in FAQ.items():
        if keyword.lower() in text_lower:
            return f"🤖 {answer}\n\n_如需人工客服，请回复「转人工」/ type \"agent\" for human support_"

    # LLM-based reply if ai_reply backend is configured
    ai_backend = router.get_backend("ai_reply")
    if ai_backend:
        try:
            faq_context = "\n".join(f"Q: {k} -> A: {v}" for k, v in FAQ.items())
            reply = await router.chat(
                "ai_reply",
                [
                    {"role": "system", "content": (
                        "You are a customer service AI assistant. Answer the user's question based on the FAQ below. "
                        "If the question is not covered by the FAQ, reply with exactly 'NO_MATCH'. "
                        "Keep answers concise and helpful. Reply in the same language as the user.\n\n"
                        f"FAQ:\n{faq_context}"
                    )},
                    {"role": "user", "content": text},
                ],
                temperature=0.3,
                max_tokens=300,
                timeout=8,
            )
            if reply and reply.strip() != "NO_MATCH":
                return f"🤖 {reply}\n\n_如需人工客服，请回复「转人工」/ type \"agent\" for human support_"
        except Exception as e:
            logger.warning("AI reply failed: %s", e)

    return None


# =============================================================================
# Reply Timeout Monitor
# =============================================================================

async def _timeout_alert(manager: ChannelManager, session_id: str, topic_id: int) -> None:
    """Wait for timeout, then alert agents."""
    await asyncio.sleep(cfg.reply_timeout)

    # Check if still pending
    if session_id not in pending_replies:
        return

    tg = manager._channels["telegram"]
    assert isinstance(tg, TelegramAdapter) and tg._app

    minutes = cfg.reply_timeout // 60
    await tg._app.bot.send_message(
        chat_id=int(cfg.support_group_id),
        message_thread_id=topic_id,
        text=f"⏰ 用户已等待 {minutes} 分钟未收到回复！请尽快处理。",
    )
    pending_replies.pop(session_id, None)


def start_reply_timer(manager: ChannelManager, session_id: str, topic_id: int) -> None:
    if not cfg.features.timeout_alerts:
        return
    # Cancel existing timer
    old = pending_replies.pop(session_id, None)
    if old:
        old.cancel()
    pending_replies[session_id] = asyncio.create_task(
        _timeout_alert(manager, session_id, topic_id)
    )


def cancel_reply_timer(session_id: str) -> None:
    task = pending_replies.pop(session_id, None)
    if task:
        task.cancel()


# =============================================================================
# Forward: User -> Telegram (with language detection + sensitive filter)
# =============================================================================

async def forward_to_telegram(manager: ChannelManager, msg: UnifiedMessage) -> None:
    session_id = msg.chat_id
    if not session_id:
        return

    # If queue feature is on and this session is queued, just acknowledge
    if cfg.features.queue and session_id in waiting_queue:
        pos = waiting_queue.index(session_id) + 1
        user_ch = _find_user_channel(manager, session_id)
        if user_ch:
            await user_ch.send(OutboundMessage(
                chat_id=session_id,
                text=f"您前面还有 {pos} 位用户等待，请耐心等候",
            ))
        return

    user_info = msg.metadata.get("user_info", {})
    topic_id = await get_or_create_topic(manager, session_id, user_info, msg.channel)

    # Check if session has no agent (all busy) — queue it (gated)
    if cfg.features.queue and cfg.agents and not await store.get_assigned_agent(session_id):
        if session_id not in waiting_queue:
            waiting_queue.append(session_id)
            pos = len(waiting_queue)
            user_ch = _find_user_channel(manager, session_id)
            if user_ch:
                await user_ch.send(OutboundMessage(
                    chat_id=session_id,
                    text=f"当前客服繁忙，您前面还有 {pos} 位用户等待，请耐心等候",
                ))
            tg = manager._channels["telegram"]
            assert isinstance(tg, TelegramAdapter) and tg._app
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id),
                message_thread_id=topic_id,
                text=f"⏳ 所有客服已满，用户已进入排队 (队列位置: {pos})",
            )
        return

    text = msg.content.text or ""

    # Detect and store user language (on first text message) — gated by translation feature
    if cfg.features.translation and msg.content.type == ContentType.TEXT and text:
        lang = await detect_language(text)
        current_lang = await store.get_user_lang(session_id)
        if current_lang == "zh" and lang != "zh":
            await store.set_user_lang(session_id, lang)
            logger.info("session %s language detected: %s", session_id, lang)

    # Sensitive word check — gated
    if cfg.features.sensitive_filter:
        matched = check_sensitive(text)
        if matched:
            await store.log_sensitive(session_id, text, matched)
            # Notify agent, but still forward
            tg = manager._channels["telegram"]
            assert isinstance(tg, TelegramAdapter) and tg._app
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id),
                message_thread_id=topic_id,
                text=f"⚠️ 敏感词检测: {', '.join(matched)}",
            )

    # Persist message
    await store.add_message(
        session_id, "user", text,
        media_url=msg.content.media_url, media_type=msg.content.media_type,
    )

    # AI auto-reply — gated
    if cfg.features.ai_reply and msg.content.type == ContentType.TEXT and text:
        if text.strip() in ("转人工", "agent", "human"):
            cancel_reply_timer(session_id)
            tg = manager._channels["telegram"]
            assert isinstance(tg, TelegramAdapter) and tg._app
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id),
                message_thread_id=topic_id,
                text=f"👤 用户请求转人工\n\n> {text}",
            )
            start_reply_timer(manager, session_id, topic_id)
            return

        ai_reply = await try_ai_reply(text)
        if ai_reply:
            await store.add_message(session_id, "agent", ai_reply)
            user_ch = _find_user_channel(manager, session_id)
            if user_ch:
                await user_ch.send(OutboundMessage(chat_id=session_id, text=ai_reply))
            tg = manager._channels["telegram"]
            assert isinstance(tg, TelegramAdapter) and tg._app
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id),
                message_thread_id=topic_id,
                text=f"👤 {text}\n\n🤖 _{ai_reply}_",
                parse_mode="Markdown",
            )
            return

    # Forward to Telegram
    tg = manager._channels["telegram"]
    assert isinstance(tg, TelegramAdapter) and tg._app

    # Translate user message for agent if not Chinese — gated
    user_lang = await store.get_user_lang(session_id)
    display_text = text

    if cfg.features.translation and user_lang != "zh" and text and router.get_backend("translate"):
        translated = await translate_text(text, "zh", user_lang)
        if translated != text:
            display_text = f"{text}\n\n🌐 _{translated}_"

    if msg.content.type == ContentType.MEDIA and msg.content.media_type in ("voice", "audio"):
        # Voice/audio message -- transcribe via Whisper, then forward both
        audio_bytes: bytes | None = None
        audio_filename = "audio.ogg"

        data_url = msg.content.media_url or ""
        if "," in data_url:
            # base64 data URI (e.g. from WebChat)
            _header, b64data = data_url.split(",", 1)
            audio_bytes = base64.b64decode(b64data)
        elif msg.raw:
            # Telegram Update -- download the voice/audio file
            update = msg.raw
            tg_msg = getattr(update, "message", None)
            voice = getattr(tg_msg, "voice", None) if tg_msg else None
            audio = getattr(tg_msg, "audio", None) if tg_msg else None
            file_obj = voice or audio
            if file_obj:
                tg_file = await tg._app.bot.get_file(file_obj.file_id)
                if tg_file.file_path:
                    audio_filename = tg_file.file_path.split("/")[-1] or audio_filename
                    ba = await tg_file.download_as_bytearray()
                    audio_bytes = bytes(ba)

        # Attempt transcription
        transcription: str | None = None
        if audio_bytes:
            transcription = await transcribe_audio(audio_bytes, audio_filename)

        # Forward the original audio to the agent topic
        if audio_bytes:
            buf = io.BytesIO(audio_bytes)
            buf.name = audio_filename
            await tg._app.bot.send_voice(
                chat_id=int(cfg.support_group_id),
                message_thread_id=topic_id,
                voice=buf,
                caption=display_text or None,
            )

        # Send transcription as a separate text message
        if transcription:
            transcription_display = f"🎤 语音转文字: {transcription}"
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id),
                message_thread_id=topic_id,
                text=transcription_display,
            )
            await store.add_message(session_id, "user", transcription_display)

    elif msg.content.type == ContentType.MEDIA and msg.content.media_url:
        media_type = msg.content.media_type or "image"
        data_url = msg.content.media_url
        # filename may come from metadata (webchat) or raw update (telegram)
        filename = msg.metadata.get("filename") or ""

        if "," in data_url:
            header, b64data = data_url.split(",", 1)
            raw = base64.b64decode(b64data)
            buf = io.BytesIO(raw)
            if media_type == "document":
                buf.name = filename or "document"
                await tg._app.bot.send_document(
                    chat_id=int(cfg.support_group_id),
                    message_thread_id=topic_id,
                    document=buf,
                    caption=display_text or None,
                )
            elif media_type == "video":
                buf.name = "video.mp4"
                await tg._app.bot.send_video(
                    chat_id=int(cfg.support_group_id),
                    message_thread_id=topic_id,
                    video=buf,
                    caption=display_text or None,
                )
            else:
                buf.name = "image.jpg"
                await tg._app.bot.send_photo(
                    chat_id=int(cfg.support_group_id),
                    message_thread_id=topic_id,
                    photo=buf,
                    caption=display_text or None,
                )
        else:
            if media_type == "document":
                await tg._app.bot.send_document(
                    chat_id=int(cfg.support_group_id),
                    message_thread_id=topic_id,
                    document=data_url,
                    caption=display_text or None,
                )
            elif media_type == "video":
                await tg._app.bot.send_video(
                    chat_id=int(cfg.support_group_id),
                    message_thread_id=topic_id,
                    video=data_url,
                    caption=display_text or None,
                )
            else:
                await tg._app.bot.send_photo(
                    chat_id=int(cfg.support_group_id),
                    message_thread_id=topic_id,
                    photo=data_url,
                    caption=display_text or None,
                )
    else:
        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id),
            message_thread_id=topic_id,
            text=display_text or "(empty)",
            parse_mode="Markdown",
        )

    # Start reply timeout timer (gated inside start_reply_timer)
    start_reply_timer(manager, session_id, topic_id)


# =============================================================================
# Forward: Telegram -> User (with auto-translation)
# =============================================================================

async def forward_to_user(manager: ChannelManager, msg: UnifiedMessage) -> None:
    if not msg.thread_id:
        return

    topic_id = int(msg.thread_id)
    session_id = topic_to_session.get(topic_id)

    if not session_id:
        db_session = await store.get_session_by_topic(topic_id)
        if db_session:
            session_id = db_session["session_id"]
            session_to_topic[session_id] = topic_id
            topic_to_session[topic_id] = session_id

    if not session_id:
        return

    # Handle commands
    if msg.content.type == ContentType.COMMAND:
        # Import here to avoid circular import — handlers imports from forwarding
        from .handlers import handle_agent_command
        await handle_agent_command(manager, msg, session_id, topic_id)
        return

    # Cancel reply timer (agent responded)
    cancel_reply_timer(session_id)
    await store.set_first_reply(session_id)

    agent_text = msg.content.text or ""

    # Auto-translate agent reply to user's language — gated
    user_lang = await store.get_user_lang(session_id)
    translated_text = agent_text

    if cfg.features.translation and user_lang != "zh" and agent_text and router.get_backend("translate"):
        translated_text = await translate_text(agent_text, user_lang, "zh")
        if translated_text != agent_text:
            # Show original + translation to agent
            tg = manager._channels["telegram"]
            assert isinstance(tg, TelegramAdapter) and tg._app
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id),
                message_thread_id=topic_id,
                text=f"🌐 已翻译为 [{user_lang}]: _{translated_text}_",
                parse_mode="Markdown",
            )

    # Persist
    msg_id = await store.add_message(session_id, "agent", agent_text)

    user_ch = _find_user_channel(manager, session_id)
    if not user_ch:
        tg = manager._channels["telegram"]
        assert isinstance(tg, TelegramAdapter) and tg._app
        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id),
            message_thread_id=topic_id,
            text="⚠️ 用户当前离线，消息已保存。",
        )
        return

    out = OutboundMessage(chat_id=_resolve_chat_id(session_id), text=translated_text)

    if msg.content.type == ContentType.MEDIA and msg.raw:
        tg = manager._channels["telegram"]
        assert isinstance(tg, TelegramAdapter) and tg._app
        update = msg.raw
        if update.message and update.message.photo:
            photo = update.message.photo[-1]
            file = await tg._app.bot.get_file(photo.file_id)
            out.media_url = _telegram_file_url(file.file_path) if file.file_path else None
            out.media_type = "image"
        elif update.message and update.message.video:
            video = update.message.video
            file = await tg._app.bot.get_file(video.file_id)
            out.media_url = _telegram_file_url(file.file_path) if file.file_path else None
            out.media_type = "video"
        elif update.message and update.message.voice:
            voice_obj = update.message.voice
            file = await tg._app.bot.get_file(voice_obj.file_id)
            out.media_url = _telegram_file_url(file.file_path) if file.file_path else None
            out.media_type = "voice"
        elif update.message and update.message.audio:
            audio_obj = update.message.audio
            file = await tg._app.bot.get_file(audio_obj.file_id)
            out.media_url = _telegram_file_url(file.file_path) if file.file_path else None
            out.media_type = "audio"
            out.metadata["filename"] = audio_obj.file_name or "audio"
        elif update.message and update.message.document:
            doc = update.message.document
            file = await tg._app.bot.get_file(doc.file_id)
            out.media_url = _telegram_file_url(file.file_path) if file.file_path else None
            out.media_type = "document"
            out.metadata["filename"] = doc.file_name or "document"

    await user_ch.send(out)
    # User is online and received the message — mark as seen
    await store.set_last_seen(session_id, msg_id)
    logger.info("forwarded reply to %s (lang=%s)", session_id, user_lang)


# =============================================================================
# Callback (ratings)
# =============================================================================

async def handle_callback(manager: ChannelManager, msg: UnifiedMessage) -> None:
    if not cfg.features.ratings:
        return

    data = msg.content.callback_data or ""
    if data.startswith("rate:"):
        parts = data.split(":")
        if len(parts) == 3:
            session_id = parts[1]
            score = int(parts[2])
            await store.add_rating(session_id, score)

            user_ch = _find_user_channel(manager, session_id)
            if user_ch:
                user_lang = await store.get_user_lang(session_id)
                thanks = "感谢您的评价！祝您生活愉快！"
                if cfg.features.translation and user_lang != "zh" and router.get_backend("translate"):
                    thanks = await translate_text(thanks, user_lang, "zh")
                await user_ch.send(OutboundMessage(
                    chat_id=session_id, text=f"{'⭐' * score} {thanks}",
                ))

            if session_id in session_to_topic:
                topic_id = session_to_topic[session_id]
                tg = manager._channels["telegram"]
                assert isinstance(tg, TelegramAdapter) and tg._app
                await tg._app.bot.send_message(
                    chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                    text=f"⭐ 用户评价: {score}/5 {'⭐' * score}",
                )


# =============================================================================
# Online/Offline + History
# =============================================================================

async def notify_user_online(manager: ChannelManager, session_id: str) -> None:
    if not cfg.features.online_status:
        return
    if session_id not in session_to_topic:
        return
    topic_id = session_to_topic[session_id]
    tg = manager._channels["telegram"]
    assert isinstance(tg, TelegramAdapter) and tg._app
    await tg._app.bot.send_message(
        chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
        text="🟢 用户已上线",
    )


async def notify_user_offline(manager: ChannelManager, session_id: str) -> None:
    if not cfg.features.online_status:
        return
    if session_id not in session_to_topic:
        return
    topic_id = session_to_topic[session_id]
    tg = manager._channels["telegram"]
    assert isinstance(tg, TelegramAdapter) and tg._app
    try:
        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
            text="🔴 用户已离线",
        )
    except Exception:
        pass


async def send_history(manager: ChannelManager, session_id: str) -> None:
    if not cfg.features.history:
        return
    messages = await store.get_unseen_messages(session_id, limit=50)
    if not messages:
        return
    user_ch = _find_user_channel(manager, session_id)
    if not user_ch:
        return
    if hasattr(user_ch, '_sessions'):
        ws = user_ch._sessions.get(session_id)
        if ws and not ws.closed:
            count = len(messages)
            await ws.send_json({
                "type": "unseen_notice",
                "count": count,
            })
            await ws.send_json({
                "type": "history",
                "messages": [
                    {
                        "sender": m["sender"],
                        "text": m["content"],
                        "media_url": m.get("media_url"),
                        "media_type": m.get("media_type"),
                        "timestamp": m["timestamp"],
                    }
                    for m in messages
                ],
            })
            # Mark all sent messages as seen
            last_id = messages[-1]["id"]
            await store.set_last_seen(session_id, last_id)


# =============================================================================
# Helpers
# =============================================================================

def _resolve_chat_id(session_id: str) -> str:
    """Resolve session_id to actual chat_id for sending messages.

    "tg_12345" -> "12345", "wa_1234567890" -> "1234567890", etc.
    All DM session IDs use the pattern: {prefix}_{user_id}
    """
    from .channels import CHANNEL_BY_PREFIX
    for prefix in CHANNEL_BY_PREFIX:
        tag = f"{prefix}_"
        if session_id.startswith(tag):
            return session_id[len(tag):]
    return session_id


def _find_user_channel(manager: ChannelManager, session_id: str):
    # DM sessions — match any channel prefix
    if session_id in dm_sessions:
        from .channels import CHANNEL_BY_PREFIX
        for prefix, ch_def in CHANNEL_BY_PREFIX.items():
            if session_id.startswith(f"{prefix}_"):
                # Telegram DM uses the "telegram" adapter, not "telegram_dm"
                ch_id = "telegram" if ch_def.channel_id == "telegram" else ch_def.channel_id
                return manager._channels.get(ch_id)

    for ch_name in ("webchat", "wkim"):
        ch = manager._channels.get(ch_name)
        if not ch:
            continue
        sessions = getattr(ch, '_connections', None) or getattr(ch, '_sessions', None)
        if sessions and session_id in sessions:
            return ch
    return None


# =============================================================================
# DM channels (Telegram private chat / WhatsApp -> support group)
# =============================================================================

WELCOME_MSG = "您好！欢迎联系客服，请描述您的问题，我们会尽快回复。"


async def handle_dm(manager: ChannelManager, msg: UnifiedMessage, prefix: str, channel_name: str) -> None:
    """Handle private/DM messages from Telegram or WhatsApp users."""
    user_id = msg.sender.id
    if not user_id:
        return

    session_id = f"{prefix}_{user_id}"

    is_start = msg.content.type == ContentType.COMMAND and msg.content.command == "start"
    is_new = session_id not in dm_sessions and session_id not in session_to_topic

    if is_new or is_start:
        dm_sessions.add(session_id)
        session_channel[session_id] = channel_name

        user_info = {
            "user_type": "authenticated",
            "user_id": user_id,
            "name": msg.sender.display_name or msg.sender.username or user_id,
        }
        if is_start and msg.content.args:
            user_info["ref"] = msg.content.args[0]

        await get_or_create_topic(manager, session_id, user_info, channel_name)

        # Send welcome
        adapter = manager._channels.get(msg.channel)
        if adapter:
            await adapter.send(OutboundMessage(
                chat_id=_resolve_chat_id(session_id),
                text=WELCOME_MSG,
            ))

        if is_start:
            return

    # Ensure session is tracked
    if session_id not in dm_sessions:
        dm_sessions.add(session_id)
        session_channel[session_id] = channel_name

    # Wrap and forward to support group
    wrapped = UnifiedMessage(
        id=msg.id,
        channel=channel_name,
        sender=msg.sender,
        content=msg.content,
        timestamp=msg.timestamp,
        chat_id=session_id,
        thread_id=msg.thread_id,
        reply_to_id=msg.reply_to_id,
        metadata={"user_info": {
            "user_type": "authenticated",
            "user_id": user_id,
            "name": msg.sender.display_name or msg.sender.username or user_id,
        }},
        raw=msg.raw,
    )
    from .state import msg_queue
    await msg_queue.run(session_id, forward_to_telegram(manager, wrapped))


# =============================================================================
# Serve frontend
# =============================================================================

CHAT_HTML = Path(__file__).parent / "dashboard" / "static" / "chat.html"


async def serve_chat_page(request: web.Request) -> web.Response:
    html = CHAT_HTML.read_text()
    return web.Response(text=html, content_type="text/html")
