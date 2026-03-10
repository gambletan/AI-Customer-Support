"""Tests for support.model_router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from support.model_router import BackendConfig, ModelRouter


# --- BackendConfig ---

def test_backend_chat_url():
    bc = BackendConfig(name="test", base_url="https://api.example.com/v1", api_key="sk-123", model="m1")
    assert bc.chat_url == "https://api.example.com/v1/chat/completions"


def test_backend_chat_url_trailing_slash():
    bc = BackendConfig(name="test", base_url="https://api.example.com/v1/", api_key="sk-123", model="m1")
    assert bc.chat_url == "https://api.example.com/v1/chat/completions"


def test_backend_chat_url_already_has_path():
    bc = BackendConfig(name="test", base_url="https://api.example.com/v1/chat/completions", api_key="k", model="m")
    assert bc.chat_url == "https://api.example.com/v1/chat/completions"


def test_backend_available():
    assert BackendConfig(name="x", base_url="u", api_key="key", model="m").available is True
    assert BackendConfig(name="x", base_url="u", api_key="", model="m").available is False


# --- ModelRouter.from_env ---

def test_from_env_picks_up_keys(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "mm-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    # Clear others to avoid leaking real env
    for k in ("QWEN_API_KEY", "GLM_API_KEY", "OPENAI_API_KEY", "CLAUDE_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    router = ModelRouter.from_env()
    assert router.backends["minimax"].api_key == "mm-key"
    assert router.backends["deepseek"].api_key == "ds-key"
    assert router.backends["minimax"].available is True
    assert router.backends["qwen"].available is False


def test_from_env_custom_routing(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("CS_ROUTER_TRANSLATE", "openai")
    # Clear others
    for k in ("DEEPSEEK_API_KEY", "QWEN_API_KEY", "GLM_API_KEY", "OPENAI_API_KEY", "CLAUDE_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    router = ModelRouter.from_env()
    assert router.task_routing["translate"] == "openai"


# --- get_backend ---

def test_get_backend_configured(monkeypatch):
    router = ModelRouter(
        backends={
            "minimax": BackendConfig("minimax", "u", "key", "m"),
            "deepseek": BackendConfig("deepseek", "u", "", "m"),
        },
        task_routing={"translate": "minimax"},
    )
    b = router.get_backend("translate")
    assert b is not None
    assert b.name == "minimax"


def test_get_backend_fallback():
    """When configured backend is unavailable, fall back to first available."""
    router = ModelRouter(
        backends={
            "minimax": BackendConfig("minimax", "u", "", "m"),  # unavailable
            "openai": BackendConfig("openai", "u", "ok", "m"),
        },
        task_routing={"translate": "minimax"},
    )
    b = router.get_backend("translate")
    assert b is not None
    assert b.name == "openai"


def test_get_backend_none_available():
    """Returns None when no backends have API keys."""
    router = ModelRouter(
        backends={
            "minimax": BackendConfig("minimax", "u", "", "m"),
            "openai": BackendConfig("openai", "u", "", "m"),
        },
        task_routing={"translate": "minimax"},
    )
    assert router.get_backend("translate") is None


# --- summary ---

def test_summary_output():
    router = ModelRouter(
        backends={"minimax": BackendConfig("minimax", "u", "key", "model-1")},
        task_routing={"translate": "minimax", "detect_lang": "minimax",
                      "ai_reply": "minimax", "summarize": "minimax"},
    )
    lines = router.summary()
    assert any("minimax" in line for line in lines)
    assert any("translate" in line for line in lines)


# --- chat (mocked httpx) ---

@pytest.mark.asyncio
async def test_chat_success():
    router = ModelRouter(
        backends={"minimax": BackendConfig("minimax", "https://api.example.com/v1", "key", "m1")},
        task_routing={"translate": "minimax"},
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "  Hello  "}}],
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await router.chat("translate", [{"role": "user", "content": "你好"}])

    assert result == "Hello"
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_chat_no_backend_raises():
    router = ModelRouter(backends={}, task_routing={"translate": "minimax"})
    with pytest.raises(RuntimeError, match="No available backend"):
        await router.chat("translate", [{"role": "user", "content": "hi"}])
