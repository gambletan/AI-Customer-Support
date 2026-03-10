"""Channel definitions — all supported IM channels and their env var mappings.

Each channel is auto-enabled when its required env vars are set.
Gateway reads this to dynamically instantiate adapters.

Architecture:
    ChannelDef  —  declarative definition (env keys, adapter path, QR deeplink)
    get_enabled_channels()  —  auto-detect from env vars
    create_adapter()  —  convention-based factory (ENV_KEY.lower() -> kwarg)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChannelDef:
    """Definition of a supported channel."""
    name: str                    # human-readable name
    channel_id: str              # adapter channel_id (matches msg.channel)
    prefix: str                  # DM session prefix (e.g. "wa" -> "wa_12345")
    env_prefix: str              # env var prefix (CS_WA_ -> CS_WA_ACCESS_TOKEN)
    required_keys: list[str]     # required env var suffixes (checked for non-empty)
    optional_keys: list[str]     # optional env var suffixes
    adapter_module: str          # import path under unified_channel.adapters
    adapter_class: str           # class name
    deeplink_template: str = ""  # URL template for QR code ({value} replaced)
    deeplink_env: str = ""       # env var that holds the deeplink value
    default_port: int = 0        # default webhook port (0 = no port)
    notes: str = ""              # setup hint
    # Convention overrides (most env keys map to kwarg via KEY.lower())
    type_overrides: dict[str, str] = field(default_factory=dict)  # KEY -> "int"|"bool"|"float"|"set"
    extra_kwargs: dict[str, Any] = field(default_factory=dict)    # constant kwargs not from env


# All supported channels (order = display order in setup wizard)
CHANNELS: list[ChannelDef] = [
    ChannelDef(
        name="WhatsApp",
        channel_id="whatsapp",
        prefix="wa",
        env_prefix="CS_WA_",
        required_keys=["ACCESS_TOKEN", "PHONE_NUMBER_ID", "VERIFY_TOKEN"],
        optional_keys=["APP_SECRET", "PORT", "PHONE_NUMBER"],
        adapter_module="whatsapp",
        adapter_class="WhatsAppAdapter",
        deeplink_template="https://wa.me/{value}",
        deeplink_env="CS_WA_PHONE_NUMBER",
        default_port=8443,
        notes="Meta Business Cloud API. Create app at developers.facebook.com",
        type_overrides={"PORT": "int"},
    ),
    ChannelDef(
        name="LINE",
        channel_id="line",
        prefix="line",
        env_prefix="CS_LINE_",
        required_keys=["CHANNEL_SECRET", "CHANNEL_ACCESS_TOKEN"],
        optional_keys=["PORT"],
        adapter_module="line",
        adapter_class="LineAdapter",
        deeplink_template="https://line.me/R/oaMessage/{value}",
        deeplink_env="CS_LINE_BOT_ID",
        default_port=8044,
        notes="LINE Messaging API. Create channel at developers.line.biz",
        type_overrides={"PORT": "int"},
    ),
    ChannelDef(
        name="Discord",
        channel_id="discord",
        prefix="dc",
        env_prefix="CS_DISCORD_",
        required_keys=["TOKEN"],
        optional_keys=[],
        adapter_module="discord",
        adapter_class="DiscordAdapter",
        notes="Discord Bot. Create at discord.com/developers",
        extra_kwargs={"allow_dm": True},
    ),
    ChannelDef(
        name="Slack",
        channel_id="slack",
        prefix="slack",
        env_prefix="CS_SLACK_",
        required_keys=["BOT_TOKEN", "APP_TOKEN"],
        optional_keys=[],
        adapter_module="slack",
        adapter_class="SlackAdapter",
        notes="Slack app with Socket Mode. Create at api.slack.com/apps",
    ),
    ChannelDef(
        name="WeChat (Enterprise)",
        channel_id="wechat",
        prefix="wx",
        env_prefix="CS_WECHAT_",
        required_keys=["CORP_ID", "CORP_SECRET", "AGENT_ID"],
        optional_keys=["TOKEN", "ENCODING_AES_KEY", "PORT"],
        adapter_module="wechat",
        adapter_class="WeChatAdapter",
        default_port=9001,
        notes="Enterprise WeChat. Configure at work.weixin.qq.com",
        type_overrides={"PORT": "int"},
    ),
    ChannelDef(
        name="Feishu (Lark)",
        channel_id="feishu",
        prefix="fs",
        env_prefix="CS_FEISHU_",
        required_keys=["APP_ID", "APP_SECRET"],
        optional_keys=["VERIFICATION_TOKEN", "ENCRYPT_KEY", "PORT"],
        adapter_module="feishu",
        adapter_class="FeishuAdapter",
        default_port=9000,
        notes="Feishu/Lark Bot. Create at open.feishu.cn",
        type_overrides={"PORT": "int"},
    ),
    ChannelDef(
        name="DingTalk",
        channel_id="dingtalk",
        prefix="dt",
        env_prefix="CS_DINGTALK_",
        required_keys=["APP_KEY", "APP_SECRET"],
        optional_keys=["WEBHOOK_URL", "SECRET", "PORT"],
        adapter_module="dingtalk",
        adapter_class="DingTalkAdapter",
        default_port=9002,
        notes="DingTalk Bot. Create at open.dingtalk.com",
        type_overrides={"PORT": "int"},
    ),
    ChannelDef(
        name="MS Teams",
        channel_id="msteams",
        prefix="teams",
        env_prefix="CS_TEAMS_",
        required_keys=["APP_ID", "APP_PASSWORD"],
        optional_keys=["PORT"],
        adapter_module="msteams",
        adapter_class="MSTeamsAdapter",
        default_port=3978,
        notes="Microsoft Teams Bot. Register at dev.botframework.com",
        type_overrides={"PORT": "int"},
    ),
    ChannelDef(
        name="QQ",
        channel_id="qq",
        prefix="qq",
        env_prefix="CS_QQ_",
        required_keys=["APP_ID", "TOKEN"],
        optional_keys=["SECRET", "SANDBOX"],
        adapter_module="qq",
        adapter_class="QQAdapter",
        notes="QQ Bot. Create at q.qq.com",
        type_overrides={"SANDBOX": "bool"},
    ),
    ChannelDef(
        name="Matrix",
        channel_id="matrix",
        prefix="mx",
        env_prefix="CS_MATRIX_",
        required_keys=["HOMESERVER", "USER_ID"],
        optional_keys=["PASSWORD", "ACCESS_TOKEN"],
        adapter_module="matrix",
        adapter_class="MatrixAdapter",
        notes="Matrix protocol. Any homeserver (matrix.org, Element, etc.)",
    ),
    ChannelDef(
        name="Zalo",
        channel_id="zalo",
        prefix="zalo",
        env_prefix="CS_ZALO_",
        required_keys=["ACCESS_TOKEN"],
        optional_keys=["APP_SECRET", "PORT"],
        adapter_module="zalo",
        adapter_class="ZaloAdapter",
        default_port=8060,
        notes="Zalo OA. Create at oa.zalo.me (Vietnam)",
        type_overrides={"PORT": "int"},
    ),
    ChannelDef(
        name="iMessage",
        channel_id="imessage",
        prefix="imsg",
        env_prefix="CS_IMESSAGE_",
        required_keys=["ENABLED"],
        optional_keys=["ALLOWED_NUMBERS", "POLL_INTERVAL"],
        adapter_module="imessage",
        adapter_class="IMessageAdapter",
        notes="macOS only. Requires Full Disk Access + Messages.app",
        type_overrides={"POLL_INTERVAL": "float", "ALLOWED_NUMBERS": "set"},
    ),
]

# Lookup tables (built once)
CHANNEL_BY_ID: dict[str, ChannelDef] = {ch.channel_id: ch for ch in CHANNELS}
CHANNEL_BY_PREFIX: dict[str, ChannelDef] = {ch.prefix: ch for ch in CHANNELS}


def _convert(value: str, type_name: str, default_port: int = 0) -> Any:
    """Convert env string to typed value."""
    if type_name == "int":
        return int(value) if value else default_port
    if type_name == "float":
        return float(value) if value else 0.0
    if type_name == "bool":
        return value.lower() in ("true", "1", "yes")
    if type_name == "set":
        return {s.strip() for s in value.split(",") if s.strip()} if value else None
    return value


def get_enabled_channels() -> list[tuple[ChannelDef, dict[str, str]]]:
    """Return list of (channel_def, env_values) for channels whose required keys are set."""
    result = []
    for ch in CHANNELS:
        env_vals: dict[str, str] = {}
        all_set = True
        for key in ch.required_keys:
            val = os.environ.get(f"{ch.env_prefix}{key}", "")
            if not val:
                all_set = False
                break
            env_vals[key] = val
        if not all_set:
            continue
        for key in ch.optional_keys:
            val = os.environ.get(f"{ch.env_prefix}{key}", "")
            if val:
                env_vals[key] = val
        result.append((ch, env_vals))
    return result


def create_adapter(ch: ChannelDef, env_vals: dict[str, str]):
    """Dynamically import and instantiate the adapter.

    Convention: ENV_KEY.lower() becomes the constructor kwarg name.
    Type conversions and extra constants come from ChannelDef metadata.
    """
    import importlib
    mod = importlib.import_module(f"unified_channel.adapters.{ch.adapter_module}")
    cls = getattr(mod, ch.adapter_class)

    kwargs: dict[str, Any] = {}

    # Map all env values to constructor kwargs
    for key in ch.required_keys + ch.optional_keys:
        raw = env_vals.get(key, "")
        if not raw and key in ch.optional_keys:
            # Use default_port for PORT if not set
            if key == "PORT" and ch.default_port:
                raw = str(ch.default_port)
            else:
                continue
        kwarg_name = key.lower()
        type_name = ch.type_overrides.get(key, "str")
        kwargs[kwarg_name] = _convert(raw, type_name, ch.default_port)

    # Skip env-only keys that aren't constructor params (e.g. ENABLED, PHONE_NUMBER)
    # The adapter __init__ will raise TypeError if we pass unknown kwargs.
    # Filter by inspecting the constructor signature.
    import inspect
    sig = inspect.signature(cls.__init__)
    valid_params = set(sig.parameters.keys()) - {"self"}
    kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

    # Add constant kwargs
    kwargs.update(ch.extra_kwargs)

    return cls(**kwargs)


def get_deeplink(ch: ChannelDef) -> str | None:
    """Return the deeplink URL for a channel, or None if not configured."""
    if not ch.deeplink_template or not ch.deeplink_env:
        return None
    value = os.environ.get(ch.deeplink_env, "")
    if not value:
        return None
    return ch.deeplink_template.format(value=value)
