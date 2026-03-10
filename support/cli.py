"""CLI entry point — ai-cs [command]

Commands:
    ai-cs             Start the service (default)
    ai-cs run         Start the service
    ai-cs setup       Interactive configuration wizard
    ai-cs status      Show current config and feature status
"""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "run"

    if cmd in ("run", "start"):
        from .gateway import main_entry
        main_entry()

    elif cmd == "setup":
        from .setup import main as setup_main
        setup_main()

    elif cmd == "status":
        _show_status()

    elif cmd in ("-h", "--help", "help"):
        _show_help()

    else:
        print(f"Unknown command: {cmd}")
        print()
        _show_help()
        sys.exit(1)


def _show_status() -> None:
    """Print current config and feature toggles."""
    from .config import Config
    cfg = Config()

    print("AI Customer Support — Current Configuration")
    print()
    print(f"  Telegram token: ...{cfg.telegram_token[-8:]}" if cfg.telegram_token else "  Telegram token: (not set)")
    print(f"  Support group:  {cfg.support_group_id}" if cfg.support_group_id else "  Support group:  (not set)")
    print(f"  WebChat port:   {cfg.webchat_port}")
    print(f"  WuKongIM port:  {cfg.wkim_port}")
    print(f"  Database:       {cfg.db_path}")
    print(f"  Reply timeout:  {cfg.reply_timeout}s")
    print(f"  Agents:         {', '.join(cfg.agents) or '(none)'}")
    print()

    # LLM backends
    from .model_router import ModelRouter
    router = ModelRouter.from_env()
    print("  LLM Backends:")
    for line in router.summary():
        print(f"    {line}")
    print()

    # Features
    for line in cfg.summary():
        print(f"  {line}")

    # Readiness check
    print()
    issues = []
    if not cfg.telegram_token:
        issues.append("CS_TELEGRAM_TOKEN not set")
    if not cfg.support_group_id:
        issues.append("CS_SUPPORT_GROUP_ID not set")
    if issues:
        print(f"  Status: NOT READY — {', '.join(issues)}")
        print(f"  Run: ai-cs setup")
    else:
        print(f"  Status: READY")
        print(f"  Run: ai-cs")


def _show_help() -> None:
    print("AI Customer Support")
    print()
    print("Usage: ai-cs [command]")
    print()
    print("Commands:")
    print("  run       Start the service (default)")
    print("  setup     Interactive configuration wizard")
    print("  status    Show current config and feature status")
    print("  help      Show this help message")
