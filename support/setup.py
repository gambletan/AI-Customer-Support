"""Interactive setup wizard — generates .env config and optionally starts the service.

Usage:
    python -m support.setup
    ai-cs-setup
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Feature definitions: (env_key, label, description, default)
FEATURES = [
    ("CS_FEATURE_TRANSLATION",      "Auto Translation",      "Auto-detect language + bidirectional translation", True),
    ("CS_FEATURE_AI_REPLY",         "AI Auto-Reply",         "FAQ keyword match + LLM auto-reply for common questions", False),
    ("CS_FEATURE_QUEUE",            "Waiting Queue",         "Queue customers when all agents are busy", True),
    ("CS_FEATURE_AGENT_ASSIGNMENT", "Agent Assignment",      "Auto-assign customers to least-loaded agent", True),
    ("CS_FEATURE_SENSITIVE_FILTER", "Sensitive Word Filter",  "Detect sensitive words and alert agents", False),
    ("CS_FEATURE_RATINGS",          "Satisfaction Ratings",   "Send rating survey when session closes", True),
    ("CS_FEATURE_TICKETS",          "Ticket System",         "Create support tickets via /ticket command", True),
    ("CS_FEATURE_TIMEOUT_ALERTS",   "Timeout Alerts",        "Notify agents when reply takes too long", True),
    ("CS_FEATURE_ACCESS_CONTROL",   "Group Access Control",  "Whitelist agents, auto-kick unauthorized users", False),
    ("CS_FEATURE_REPORTS",          "Reports & Analytics",   "Daily reports, hot keyword analysis", True),
    ("CS_FEATURE_TEMPLATES",        "Quick Reply Templates", "Pre-defined reply templates via /tpl", True),
    ("CS_FEATURE_ONLINE_STATUS",    "Online/Offline Status", "Notify agents when customer connects/disconnects", True),
    ("CS_FEATURE_HISTORY",          "Message History",       "Deliver unseen messages when customer reconnects", True),
]

# LLM backends: (env_key_prefix, label, description)
LLM_BACKENDS = [
    ("MINIMAX",  "MiniMax",  "Recommended for translation (MiniMax-Text-01)"),
    ("DEEPSEEK", "DeepSeek", "Recommended for AI reply (deepseek-chat)"),
    ("OPENAI",   "OpenAI",   "GPT-4o-mini, also used for Whisper voice-to-text"),
    ("QWEN",     "Qwen",     "Alibaba Qwen (qwen-plus)"),
    ("GLM",      "GLM",      "Zhipu GLM (glm-4-flash)"),
    ("CLAUDE",   "Claude",   "Anthropic Claude"),
]


def _color(code: int, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

def _green(t: str) -> str: return _color(32, t)
def _yellow(t: str) -> str: return _color(33, t)
def _cyan(t: str) -> str: return _color(36, t)
def _dim(t: str) -> str: return _color(90, t)
def _bold(t: str) -> str: return _color(1, t)


def _ask(prompt: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    if default:
        display = f"{prompt} [{default}]: "
    else:
        display = f"{prompt}: "
    val = input(display).strip()
    return val if val else default


def _ask_yn(prompt: str, default: bool = True) -> bool:
    """Yes/no prompt."""
    hint = "Y/n" if default else "y/N"
    val = input(f"{prompt} ({hint}): ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes", "1")


def _header(title: str) -> None:
    print()
    print(_bold(f"{'=' * 50}"))
    print(_bold(f"  {title}"))
    print(_bold(f"{'=' * 50}"))
    print()


def run_setup() -> None:
    _header("AI Customer Support - Setup Wizard")
    print(_dim("This wizard will generate a .env configuration file."))
    print(_dim("Press Enter to accept defaults shown in [brackets]."))
    print()

    env: dict[str, str] = {}

    # ── Step 1: Core (required) ──────────────────────────────────────
    _header("Step 1/6: Telegram Bot (Required)")
    print("Create a bot: message @BotFather on Telegram, send /newbot")
    print("Create a supergroup with Topics/Forum mode enabled")
    print("Add the bot as admin, get group ID via @RawDataBot")
    print()

    token = _ask(_cyan("Telegram bot token"))
    while not token:
        print(_yellow("  Token is required!"))
        token = _ask(_cyan("Telegram bot token"))
    env["CS_TELEGRAM_TOKEN"] = token

    group_id = _ask(_cyan("Support group ID (starts with -100)"))
    while not group_id or not group_id.startswith("-100"):
        print(_yellow("  Group ID is required and must start with -100"))
        group_id = _ask(_cyan("Support group ID"))
    env["CS_SUPPORT_GROUP_ID"] = group_id

    # ── Step 2: Ports ────────────────────────────────────────────────
    _header("Step 2/6: Ports")

    webchat_port = _ask(_cyan("WebChat port"), "8081")
    env["WEBCHAT_PORT"] = webchat_port

    wkim_port = _ask(_cyan("WuKongIM compat port"), "8080")
    env["WKIM_PORT"] = wkim_port

    env["CS_DB_PATH"] = _ask(_cyan("Database path"), "cs_data.db")

    # ── Step 3: LLM Backends ────────────────────────────────────────
    _header("Step 3/6: LLM Backends")
    print("Configure at least one LLM for translation and AI features.")
    print("You can add more later by editing .env")
    print()

    has_any_llm = False
    for prefix, label, desc in LLM_BACKENDS:
        if _ask_yn(f"Configure {_green(label)}? {_dim(desc)}", default=(prefix == "MINIMAX")):
            api_key = _ask(f"  {label} API key")
            if api_key:
                env[f"{prefix}_API_KEY"] = api_key
                has_any_llm = True

                # Ask for custom model/base_url only if user wants
                if _ask_yn(f"  Custom model/URL for {label}?", default=False):
                    defaults = {
                        "MINIMAX": ("MiniMax-Text-01", "https://api.minimaxi.com/v1"),
                        "DEEPSEEK": ("deepseek-chat", "https://api.deepseek.com/v1"),
                        "OPENAI": ("gpt-4o-mini", "https://api.openai.com/v1"),
                        "QWEN": ("qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                        "GLM": ("glm-4-flash", "https://open.bigmodel.cn/api/paas/v4"),
                        "CLAUDE": ("claude-sonnet-4-20250514", "https://api.anthropic.com/v1"),
                    }
                    model_default, url_default = defaults.get(prefix, ("", ""))
                    model = _ask(f"  Model", model_default)
                    if model != model_default:
                        env[f"{prefix}_MODEL"] = model
                    base_url = _ask(f"  Base URL", url_default)
                    if base_url != url_default:
                        env[f"{prefix}_BASE_URL"] = base_url

    if not has_any_llm:
        print()
        print(_yellow("  Warning: No LLM configured. Translation and AI reply will not work."))
        print(_dim("  You can add API keys to .env later."))

    # Task routing
    if has_any_llm and _ask_yn("\nCustomize task routing?", default=False):
        available = [p for p, _, _ in LLM_BACKENDS if f"{p}_API_KEY" in env]
        avail_str = ", ".join(b.lower() for b in available)
        print(f"  Available backends: {_green(avail_str)}")
        for task, default_backend in [
            ("TRANSLATE", "minimax"), ("DETECT_LANG", "minimax"),
            ("AI_REPLY", "deepseek"), ("SUMMARIZE", "deepseek"),
        ]:
            val = _ask(f"  {task.lower()} backend", default_backend)
            if val != default_backend:
                env[f"CS_ROUTER_{task}"] = val

    # ── Step 4: IM Channels ─────────────────────────────────────────
    _header("Step 4/6: IM Channels")
    print("Enable additional IM channels for customers to reach you.")
    print("Each channel requires its own API credentials.")
    print("Users scan one QR code and pick their preferred channel.")
    print()

    from .channels import CHANNELS

    for ch in CHANNELS:
        if _ask_yn(f"Enable {_green(ch.name)}? {_dim(ch.notes)}", default=False):
            print(f"  Required: {', '.join(ch.required_keys)}")
            for key in ch.required_keys:
                val = _ask(f"  {ch.env_prefix}{key}")
                if val:
                    env[f"{ch.env_prefix}{key}"] = val
            if ch.optional_keys:
                if _ask_yn(f"  Configure optional settings? {_dim(', '.join(ch.optional_keys))}", default=False):
                    for key in ch.optional_keys:
                        default_val = str(ch.default_port) if key == "PORT" and ch.default_port else ""
                        val = _ask(f"  {ch.env_prefix}{key}", default_val)
                        if val:
                            env[f"{ch.env_prefix}{key}"] = val
            print()

    # Base URL for QR code (needed if behind reverse proxy)
    if _ask_yn("Set public base URL? (for QR code / reverse proxy)", default=False):
        base_url = _ask(_cyan("Base URL (e.g. https://cs.example.com)"))
        if base_url:
            env["CS_BASE_URL"] = base_url

    # ── Step 5: Agents ───────────────────────────────────────────────
    _header("Step 5/6: Agent Setup")

    if _ask_yn("Configure named agents? (for load balancing and transfer)", default=False):
        agents = _ask(_cyan("Agent names (comma-separated)"), "")
        if agents:
            env["CS_AGENTS"] = agents
        max_per = _ask("Max sessions per agent", "5")
        if max_per != "5":
            env["CS_MAX_SESSIONS_PER_AGENT"] = max_per

    if _ask_yn("Restrict group access? (whitelist agent Telegram user IDs)", default=False):
        ids = _ask(_cyan("Allowed agent user IDs (comma-separated)"))
        if ids:
            env["CS_ALLOWED_AGENTS"] = ids

    timeout = _ask("Reply timeout seconds (0 = off)", "180")
    if timeout != "180":
        env["CS_REPLY_TIMEOUT"] = timeout

    # ── Step 6: Features ─────────────────────────────────────────────
    _header("Step 6/6: Features")
    print("Enable/disable optional features. Core message routing is always on.")
    print()

    for env_key, label, desc, default in FEATURES:
        enabled = _ask_yn(f"{_green(label)} — {_dim(desc)}", default=default)
        if enabled != default:
            env[env_key] = "true" if enabled else "false"

    # ── Generate .env ────────────────────────────────────────────────
    _header("Configuration Complete")

    env_path = Path.cwd() / ".env"
    if env_path.exists():
        if not _ask_yn(f".env already exists at {env_path}. Overwrite?", default=False):
            # Write to .env.new instead
            env_path = Path.cwd() / ".env.new"
            print(f"  Writing to {env_path} instead.")

    lines = [
        "# AI Customer Support Configuration",
        "# Generated by: python -m support.setup",
        "",
        "# === Core (Required) ===",
        f"CS_TELEGRAM_TOKEN={env.get('CS_TELEGRAM_TOKEN', '')}",
        f"CS_SUPPORT_GROUP_ID={env.get('CS_SUPPORT_GROUP_ID', '')}",
        "",
        "# === Ports ===",
        f"WEBCHAT_PORT={env.get('WEBCHAT_PORT', '8081')}",
        f"WKIM_PORT={env.get('WKIM_PORT', '8080')}",
        f"CS_DB_PATH={env.get('CS_DB_PATH', 'cs_data.db')}",
        "",
        "# === LLM Backends ===",
    ]

    for prefix, label, _ in LLM_BACKENDS:
        key = f"{prefix}_API_KEY"
        if key in env:
            lines.append(f"{key}={env[key]}")
            for suffix in ("_MODEL", "_BASE_URL"):
                k = f"{prefix}{suffix}"
                if k in env:
                    lines.append(f"{k}={env[k]}")

    # IM Channels
    channel_keys = [k for k in env if any(k.startswith(ch.env_prefix) for ch in CHANNELS)]
    if channel_keys:
        lines.append("")
        lines.append("# === IM Channels ===")
        for k in sorted(channel_keys):
            lines.append(f"{k}={env[k]}")
    if "CS_BASE_URL" in env:
        lines.append(f"CS_BASE_URL={env['CS_BASE_URL']}")

    # Task routing
    routing_keys = [k for k in env if k.startswith("CS_ROUTER_")]
    if routing_keys:
        lines.append("")
        lines.append("# === Task Routing ===")
        for k in sorted(routing_keys):
            lines.append(f"{k}={env[k]}")

    # Agents
    agent_keys = ["CS_AGENTS", "CS_ALLOWED_AGENTS", "CS_MAX_SESSIONS_PER_AGENT"]
    agent_lines = [f"{k}={env[k]}" for k in agent_keys if k in env]
    if agent_lines:
        lines.append("")
        lines.append("# === Agents ===")
        lines.extend(agent_lines)

    if "CS_REPLY_TIMEOUT" in env:
        lines.append(f"CS_REPLY_TIMEOUT={env['CS_REPLY_TIMEOUT']}")

    # Features (only write non-defaults)
    feature_lines = [f"{k}={env[k]}" for k, _, _, _ in FEATURES if k in env]
    if feature_lines:
        lines.append("")
        lines.append("# === Feature Toggles ===")
        lines.extend(feature_lines)

    lines.append("")

    content = "\n".join(lines)
    env_path.write_text(content)

    print(f"  {_green('Saved:')} {env_path}")
    print()

    # Show summary
    print(_bold("  Configuration Summary:"))
    print(f"  Telegram: ...{token[-8:]}")
    print(f"  Group:    {group_id}")
    print(f"  WebChat:  :{webchat_port}  WuKongIM: :{wkim_port}")

    llm_names = [label for prefix, label, _ in LLM_BACKENDS if f"{prefix}_API_KEY" in env]
    print(f"  LLM:      {', '.join(llm_names) or 'none'}")

    enabled_features = []
    disabled_features = []
    for env_key, label, _, default in FEATURES:
        is_on = env.get(env_key, str(default)).lower() in ("true", "1", "yes", "on") if env_key in env else default
        if is_on:
            enabled_features.append(label)
        else:
            disabled_features.append(label)

    print(f"  Features: {len(enabled_features)} on, {len(disabled_features)} off")
    if disabled_features:
        print(f"  Disabled:  {', '.join(disabled_features)}")
    print()

    # ── Start? ───────────────────────────────────────────────────────
    if _ask_yn("Start the service now?", default=True):
        print()
        print(_green("Starting AI Customer Support..."))
        print(_dim("Press Ctrl+C to stop."))
        print()
        os.execvp(sys.executable, [sys.executable, "-m", "support.telegram_gateway"])
    else:
        print()
        print("To start later:")
        print(f"  {_cyan('python -m support.telegram_gateway')}")
        print(f"  {_dim('or: ai-cs')}")


def main() -> None:
    try:
        run_setup()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(1)
    except EOFError:
        print("\n\nSetup cancelled.")
        sys.exit(1)


if __name__ == "__main__":
    main()
