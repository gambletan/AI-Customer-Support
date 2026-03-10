"""Centralized configuration with feature toggles."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / ".env", override=True)


def _bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes", "on")


@dataclass
class Features:
    """Feature toggles — all default to sensible values."""

    translation: bool = _bool("CS_FEATURE_TRANSLATION", True)
    ai_reply: bool = _bool("CS_FEATURE_AI_REPLY", False)
    queue: bool = _bool("CS_FEATURE_QUEUE", True)
    agent_assignment: bool = _bool("CS_FEATURE_AGENT_ASSIGNMENT", True)
    sensitive_filter: bool = _bool("CS_FEATURE_SENSITIVE_FILTER", False)
    ratings: bool = _bool("CS_FEATURE_RATINGS", True)
    tickets: bool = _bool("CS_FEATURE_TICKETS", True)
    timeout_alerts: bool = _bool("CS_FEATURE_TIMEOUT_ALERTS", True)
    access_control: bool = _bool("CS_FEATURE_ACCESS_CONTROL", False)
    reports: bool = _bool("CS_FEATURE_REPORTS", True)
    templates: bool = _bool("CS_FEATURE_TEMPLATES", True)
    online_status: bool = _bool("CS_FEATURE_ONLINE_STATUS", True)
    history: bool = _bool("CS_FEATURE_HISTORY", True)


@dataclass
class Config:
    """Full application config."""

    # Core (required)
    telegram_token: str = os.environ.get("CS_TELEGRAM_TOKEN", "")
    support_group_id: str = os.environ.get("CS_SUPPORT_GROUP_ID", "")

    # Ports
    webchat_port: int = int(os.environ.get("WEBCHAT_PORT", "8081"))
    wkim_port: int = int(os.environ.get("WKIM_PORT", "8080"))

    # Database
    db_path: str = os.environ.get("CS_DB_PATH", "cs_data.db")

    # Agents
    agents: list[str] = field(
        default_factory=lambda: [
            a.strip()
            for a in os.environ.get("CS_AGENTS", "").split(",")
            if a.strip()
        ]
    )
    allowed_agent_ids: set[str] = field(
        default_factory=lambda: {
            a.strip()
            for a in os.environ.get("CS_ALLOWED_AGENTS", "").split(",")
            if a.strip()
        }
    )
    max_sessions_per_agent: int = int(
        os.environ.get("CS_MAX_SESSIONS_PER_AGENT", "5")
    )

    # WhatsApp (optional)
    wa_access_token: str = os.environ.get("CS_WA_ACCESS_TOKEN", "")
    wa_phone_number_id: str = os.environ.get("CS_WA_PHONE_NUMBER_ID", "")
    wa_verify_token: str = os.environ.get("CS_WA_VERIFY_TOKEN", "")
    wa_app_secret: str = os.environ.get("CS_WA_APP_SECRET", "")
    wa_port: int = int(os.environ.get("CS_WA_PORT", "8443"))
    wa_phone_number: str = os.environ.get("CS_WA_PHONE_NUMBER", "")  # for wa.me link

    @property
    def wa_enabled(self) -> bool:
        return bool(self.wa_access_token and self.wa_phone_number_id and self.wa_verify_token)

    # Timeouts
    reply_timeout: int = int(os.environ.get("CS_REPLY_TIMEOUT", "180"))
    health_interval: int = int(os.environ.get("CS_HEALTH_INTERVAL", "30"))

    # LLM
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    minimax_api_key: str = os.environ.get("MINIMAX_API_KEY", "")

    # Features
    features: Features = field(default_factory=Features)

    def validate(self) -> list[str]:
        """Return list of error messages. Empty = valid."""
        errors = []
        if not self.telegram_token:
            errors.append("CS_TELEGRAM_TOKEN is required")
        if not self.support_group_id:
            errors.append("CS_SUPPORT_GROUP_ID is required")
        elif not self.support_group_id.startswith("-100"):
            errors.append("CS_SUPPORT_GROUP_ID must start with -100")
        return errors

    def summary(self) -> list[str]:
        """Human-readable config summary for logging."""
        lines = ["Features enabled:"]
        for fname in vars(self.features):
            if not fname.startswith("_"):
                val = getattr(self.features, fname)
                icon = "+" if val else "-"
                lines.append(f"  {icon} {fname}")
        return lines
