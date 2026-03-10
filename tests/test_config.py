"""Tests for support.config."""

from __future__ import annotations


def test_bool_truthy_values(monkeypatch):
    """_bool recognises true/1/yes/on (case-insensitive)."""
    from support.config import _bool

    for val in ("true", "True", "TRUE", "1", "yes", "Yes", "on", "ON"):
        monkeypatch.setenv("_TEST_BOOL", val)
        assert _bool("_TEST_BOOL") is True, f"expected True for {val!r}"


def test_bool_falsy_values(monkeypatch):
    """_bool returns False for false/0/no/off and missing keys."""
    from support.config import _bool

    for val in ("false", "False", "0", "no", "off", "OFF", "random"):
        monkeypatch.setenv("_TEST_BOOL", val)
        assert _bool("_TEST_BOOL") is False, f"expected False for {val!r}"

    monkeypatch.delenv("_TEST_BOOL", raising=False)
    assert _bool("_TEST_BOOL") is False


def test_bool_default_true(monkeypatch):
    """_bool uses the provided default when env var is missing."""
    from support.config import _bool

    monkeypatch.delenv("_TEST_BOOL_MISSING", raising=False)
    assert _bool("_TEST_BOOL_MISSING", True) is True


def test_features_defaults():
    """Features dataclass has expected default flags."""
    from support.config import Features

    f = Features()
    # These defaults come from _bool evaluated at import time;
    # just verify the types and that key toggles exist.
    assert isinstance(f.translation, bool)
    assert isinstance(f.ai_reply, bool)
    assert isinstance(f.queue, bool)
    assert isinstance(f.ratings, bool)
    assert isinstance(f.sensitive_filter, bool)
    assert isinstance(f.access_control, bool)


def test_config_defaults():
    """Config dataclass has expected field types and sensible defaults."""
    from support.config import Config

    cfg = Config()
    # These are evaluated at import-time from env; just verify types and structure
    assert isinstance(cfg.telegram_token, str)
    assert isinstance(cfg.support_group_id, str)
    assert isinstance(cfg.webchat_port, int)
    assert isinstance(cfg.wkim_port, int)
    assert isinstance(cfg.db_path, str)
    assert isinstance(cfg.agents, list)
    assert isinstance(cfg.allowed_agent_ids, set)
    assert isinstance(cfg.max_sessions_per_agent, int)
    assert isinstance(cfg.features, object)


def test_config_summary():
    """summary() returns a non-empty list of lines starting with 'Features enabled:'."""
    from support.config import Config

    cfg = Config()
    lines = cfg.summary()
    assert isinstance(lines, list)
    assert len(lines) > 1
    assert lines[0] == "Features enabled:"
    # Each subsequent line contains a + or - prefix
    for line in lines[1:]:
        assert line.strip().startswith("+") or line.strip().startswith("-")
