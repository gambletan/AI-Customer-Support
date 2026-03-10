"""Agent command handlers for Telegram support group.

Slash commands: /erp, /order, /ticket, /tpl, /close, /history,
/report, /hotwords, /queue, /transfer, /lang, /help
"""

from __future__ import annotations

from unified_channel import ChannelManager
from unified_channel.adapters.telegram import TelegramAdapter
from unified_channel.types import (
    Button,
    OutboundMessage,
    UnifiedMessage,
)

from .state import (
    TEMPLATES,
    cfg,
    logger,
    router,
    session_to_topic,
    store,
    waiting_queue,
)
from .forwarding import (
    _dequeue_next,
    _find_user_channel,
    cancel_reply_timer,
)
from .erp import create_erp_adapter
from .translation import translate_text

erp = create_erp_adapter()


async def handle_agent_command(
    manager: ChannelManager, msg: UnifiedMessage, session_id: str, topic_id: int
) -> None:
    tg = manager._channels["telegram"]
    assert isinstance(tg, TelegramAdapter) and tg._app
    cmd = msg.content.command
    args = msg.content.args

    if cmd == "erp":
        user_id = args[0] if args else None
        if not user_id:
            db_session = store.get_session(session_id)
            user_id = db_session.get("user_id") if db_session else None

        if user_id:
            customer = await erp.get_customer(user_id)
            erp_info = customer.format() if customer else f"⚠️ 未找到客户: `{user_id}`"
        else:
            erp_info = "⚠️ 该用户未登录，无法查询。"

        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
            text=erp_info, parse_mode="Markdown",
        )

    elif cmd == "order":
        query = args[0] if args else None
        if not query:
            db_session = store.get_session(session_id)
            query = db_session.get("user_phone") or db_session.get("user_id") if db_session else None

        if query:
            orders = await erp.get_orders(query)
            if orders:
                lines = [f"📦 订单查询: `{query}`\n"]
                for i, o in enumerate(orders, 1):
                    lines.append(f"{i}. {o.format_line()}")
                order_info = "\n".join(lines)
            else:
                order_info = f"📦 `{query}` 暂无订单记录。"
        else:
            order_info = "⚠️ 请提供手机号或客户ID: `/order 13800138000`"

        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
            text=order_info, parse_mode="Markdown",
        )

    elif cmd == "tpl":
        if not cfg.features.templates:
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="⚠️ 模板功能已关闭。",
            )
            return

        if not args:
            # List all templates
            lines = ["📝 快捷回复模板:\n"]
            for name in TEMPLATES:
                lines.append(f"• `/tpl {name}`")
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="\n".join(lines), parse_mode="Markdown",
            )
        else:
            tpl_name = args[0]
            tpl_text = TEMPLATES.get(tpl_name)
            if tpl_text:
                # Auto-translate template if needed — gated
                user_lang = store.get_user_lang(session_id)
                send_text = tpl_text
                if cfg.features.translation and user_lang != "zh" and router.get_backend("translate"):
                    send_text = await translate_text(tpl_text, user_lang, "zh")

                store.add_message(session_id, "agent", tpl_text)
                cancel_reply_timer(session_id)
                store.set_first_reply(session_id)

                user_ch = _find_user_channel(manager, session_id)
                if user_ch:
                    await user_ch.send(OutboundMessage(chat_id=session_id, text=send_text))
                    await tg._app.bot.send_message(
                        chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                        text=f"✅ 已发送模板「{tpl_name}」" + (f"\n🌐 {send_text}" if send_text != tpl_text else ""),
                    )
                else:
                    await tg._app.bot.send_message(
                        chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                        text="⚠️ 用户离线，模板消息已保存。",
                    )
            else:
                await tg._app.bot.send_message(
                    chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                    text=f"⚠️ 模板「{tpl_name}」不存在。输入 `/tpl` 查看所有模板。",
                    parse_mode="Markdown",
                )

    elif cmd == "ticket":
        if not cfg.features.tickets:
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="⚠️ 工单功能已关闭。",
            )
            return

        title = " ".join(args) if args else "客户问题"
        ticket_id = store.create_ticket(session_id, title, msg.sender.display_name or "")
        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
            text=f"🎫 工单已创建\n• ID: #{ticket_id}\n• 标题: {title}\n• 状态: open",
        )

    elif cmd == "close":
        store.close_session(session_id)
        cancel_reply_timer(session_id)

        user_ch = _find_user_channel(manager, session_id)
        if user_ch and cfg.features.ratings:
            # Translate rating prompt if needed — gated
            user_lang = store.get_user_lang(session_id)
            rating_text = "感谢您的咨询！请为本次服务评分："
            if cfg.features.translation and user_lang != "zh" and router.get_backend("translate"):
                rating_text = await translate_text(rating_text, user_lang, "zh")

            await user_ch.send(OutboundMessage(
                chat_id=session_id, text=rating_text,
                buttons=[
                    [
                        Button(label="⭐", callback_data=f"rate:{session_id}:1"),
                        Button(label="⭐⭐", callback_data=f"rate:{session_id}:2"),
                        Button(label="⭐⭐⭐", callback_data=f"rate:{session_id}:3"),
                        Button(label="⭐⭐⭐⭐", callback_data=f"rate:{session_id}:4"),
                        Button(label="⭐⭐⭐⭐⭐", callback_data=f"rate:{session_id}:5"),
                    ],
                ],
            ))

        close_msg = "✅ 会话已关闭"
        if cfg.features.ratings and user_ch:
            close_msg += "，已发送评价请求。"
        else:
            close_msg += "。"

        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
            text=close_msg,
        )
        try:
            await tg._app.bot.close_forum_topic(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
            )
        except Exception:
            pass

        # Dequeue next waiting customer — gated
        if cfg.features.queue:
            await _dequeue_next(manager)

    elif cmd == "history":
        limit = int(args[0]) if args else 20
        messages = store.get_messages(session_id, limit=limit)
        if messages:
            lines = [f"📜 最近 {len(messages)} 条消息:"]
            for m in messages:
                role = "👤" if m["sender"] == "user" else "💬"
                text = m["content"][:80]
                lines.append(f"{role} {m['timestamp']}: {text}")
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="\n".join(lines),
            )
        else:
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="暂无历史消息。",
            )

    elif cmd == "report":
        if not cfg.features.reports:
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="⚠️ 报表功能已关闭。",
            )
            return

        date = args[0] if args else None
        report = store.daily_report(date)
        avg_reply = f"{report['avg_first_reply_seconds']}s" if report['avg_first_reply_seconds'] else "N/A"
        lines = [
            f"📊 日报 {report['date']}\n",
            f"• 总会话: {report['total_sessions']}",
            f"• 已关闭: {report['closed_sessions']}",
            f"• 总消息: {report['total_messages']}",
            f"• 平均评分: {report['avg_rating'] or 'N/A'}",
            f"• 平均首次响应: {avg_reply}",
        ]
        if report['agents']:
            lines.append("\n👥 客服工作量:")
            for a in report['agents']:
                lines.append(f"  • {a['assigned_agent']}: {a['sessions']}会话 / {a['replies']}回复")

        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
            text="\n".join(lines),
        )

    elif cmd == "hotwords":
        if not cfg.features.reports:
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="⚠️ 报表功能已关闭。",
            )
            return

        days = int(args[0]) if args else 7
        keywords = store.hot_keywords(days=days)
        if keywords:
            lines = [f"🔥 近 {days} 天热词 Top {len(keywords)}:\n"]
            for i, (word, count) in enumerate(keywords, 1):
                lines.append(f"{i}. {word} ({count}次)")
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="\n".join(lines),
            )
        else:
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="暂无数据。",
            )

    elif cmd == "queue":
        if not cfg.features.queue:
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="⚠️ 排队功能已关闭。",
            )
            return

        if not waiting_queue:
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="📭 当前排队为空。",
            )
        else:
            lines = [f"📋 排队用户 ({len(waiting_queue)}):\n"]
            for i, sid in enumerate(waiting_queue, 1):
                db_sess = store.get_session(sid)
                name = (db_sess.get("user_name") or db_sess.get("user_id") or sid[:8]) if db_sess else sid[:8]
                lines.append(f"{i}. {name} (`{sid[:8]}…`)")
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="\n".join(lines), parse_mode="Markdown",
            )

    elif cmd == "transfer":
        if not args:
            await tg._app.bot.send_message(
                chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                text="⚠️ 请指定目标客服: `/transfer <agent_name>`",
                parse_mode="Markdown",
            )
        else:
            target_agent = args[0]
            if cfg.agents and target_agent not in cfg.agents:
                await tg._app.bot.send_message(
                    chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                    text=f"⚠️ 客服「{target_agent}」不存在。可选: {', '.join(cfg.agents)}",
                )
            else:
                old_agent = store.get_assigned_agent(session_id) or "未分配"
                store.set_assigned_agent(session_id, target_agent)

                await tg._app.bot.send_message(
                    chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
                    text=f"🔀 会话已转接: {old_agent} -> {target_agent}",
                )

                # Notify customer — translate if needed
                user_ch = _find_user_channel(manager, session_id)
                if user_ch:
                    user_lang = store.get_user_lang(session_id)
                    transfer_msg = "您的会话已转接给其他客服，请稍候。"
                    if cfg.features.translation and user_lang != "zh" and router.get_backend("translate"):
                        transfer_msg = await translate_text(transfer_msg, user_lang, "zh")
                    await user_ch.send(OutboundMessage(chat_id=session_id, text=transfer_msg))

    elif cmd == "lang":
        user_lang = store.get_user_lang(session_id)
        translate_backend = router.get_backend("translate")
        if translate_backend:
            translate_status = f"已启用 ({translate_backend.name}/{translate_backend.model})"
        else:
            translate_status = "未配置 (设置 MINIMAX_API_KEY 或 OPENAI_API_KEY)"
        await tg._app.bot.send_message(
            chat_id=int(cfg.support_group_id), message_thread_id=topic_id,
            text=f"🌐 用户语言: {user_lang}\n翻译: {translate_status}",
        )

    elif cmd == "help":
        await _send_help(tg, topic_id)


async def _send_help(tg: TelegramAdapter, topic_id: int) -> None:
    """Build /help output dynamically based on enabled features."""
    lines = ["📖 客服命令:\n", "**查询**"]
    lines.append("• `/erp [ID]` — ERP 用户信息")
    lines.append("• `/order [手机/ID]` — 订单查询")
    lines.append("• `/history [N]` — 聊天记录")

    if cfg.features.translation:
        lines.append("• `/lang` — 用户语言")

    lines.append("\n**操作**")

    if cfg.features.templates:
        lines.append("• `/tpl [名称]` — 快捷回复模板")
    if cfg.features.tickets:
        lines.append("• `/ticket 标题` — 创建工单")

    lines.append("• `/transfer <客服>` — 转接会话")
    lines.append("• `/close` — 关闭会话" + ("+评价" if cfg.features.ratings else ""))

    if cfg.features.queue:
        lines.append("• `/queue` — 查看排队用户")

    if cfg.features.reports:
        lines.append("\n**报表**")
        lines.append("• `/report [日期]` — 日报统计")
        lines.append("• `/hotwords [天数]` — 热词分析")

    if cfg.features.translation:
        lines.append("\n💡 翻译自动进行，无需手动操作")

    assert tg._app
    await tg._app.bot.send_message(
        chat_id=int(cfg.support_group_id),
        message_thread_id=topic_id,
        text="\n".join(lines),
        parse_mode="Markdown",
    )
