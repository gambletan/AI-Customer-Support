"""Telegram Gateway — thin re-export for backwards compatibility.

All logic has been split into:
    support.state        — shared runtime state (cfg, store, router, caches)
    support.translation  — detect_language(), translate_text()
    support.forwarding   — forward_to_telegram/user, topic mgmt, callbacks
    support.handlers     — agent slash-command handlers
    support.gateway      — main(), main_entry(), channel setup

Entry points:
    python -m support.telegram_gateway   (this file)
    ai-cs                                (cli.py -> gateway.main_entry)
"""

from __future__ import annotations

# Re-export public API so existing imports keep working
from .gateway import main, main_entry  # noqa: F401
from .state import (  # noqa: F401
    FAQ,
    SENSITIVE_WORDS,
    TEMPLATES,
    cfg,
    logger,
    msg_queue,
    pending_replies,
    router,
    session_channel,
    session_to_topic,
    store,
    topic_to_session,
    waiting_queue,
)
from .translation import detect_language, translate_text  # noqa: F401
from .forwarding import (  # noqa: F401
    _dequeue_next,
    _find_user_channel,
    _telegram_file_url,
    _timeout_alert,
    auto_assign_agent,
    cancel_reply_timer,
    check_sensitive,
    forward_to_telegram,
    forward_to_user,
    get_or_create_topic,
    handle_callback,
    notify_user_offline,
    notify_user_online,
    send_history,
    serve_chat_page,
    start_reply_timer,
    transcribe_audio,
    try_ai_reply,
)
from .handlers import handle_agent_command, _send_help  # noqa: F401

if __name__ == "__main__":
    main_entry()
