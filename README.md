# AI Customer Support

AI-native omnichannel customer support system. One QR code, any IM, instant service.

## Architecture

```
Customer (WebChat / WuKongIM App / Telegram)
    |
    v
+-----------------------+
| Telegram Gateway      |  <-- support/telegram_gateway.py
| (aiohttp + WebSocket) |
+-----------------------+
    |
    v
+-------------------+     +-------------------+
| Telegram Supergroup|     | AI / Model Router |
| (agent topics)     |     | (multi-LLM)      |
+-------------------+     +-------------------+
    |                          |
    v                          v
+-------------------+     +-------------------+
| CS Store (SQLite)  |     | RAG Knowledge Base|
| sessions/messages  |     | (support/ai/)     |
+-------------------+     +-------------------+
```

## Features

- **Multi-channel ingress**: WebChat (WebSocket), WuKongIM-compatible (existing mobile apps), Telegram
- **Telegram supergroup routing**: each customer session gets a topic thread; agents reply in-thread
- **AI auto-reply**: FAQ matching via RAG knowledge base, with configurable escalation
- **Multi-model LLM routing**: task-based routing (translate, detect_lang, ai_reply, summarize) across MiniMax, DeepSeek, Qwen, GLM, OpenAI, Claude
- **Auto language detection + bidirectional translation**
- **Agent management**: least-load assignment, transfer, pool tracking
- **Ticket system**: identity binding, escalation workflow
- **Analytics**: daily reports, hot keyword analysis, satisfaction ratings
- **Infrastructure**: keyed async queue (per-session FIFO), channel health monitor with exponential backoff
- **Dashboard**: REST API + WebSocket + static frontend (admin panel + webchat)
- **Sensitive word filtering** and **voice-to-text** (Whisper)

## Quick Start

```bash
# Install
pip install -e ".[all-channels]"

# Configure (~/.env or environment variables)
export CS_TELEGRAM_TOKEN="your-bot-token"
export CS_SUPPORT_GROUP_ID="-100xxxxxxxxxx"
export MINIMAX_API_KEY="sk-..."

# Run
ai-cs
# or: python -m support.telegram_gateway
```

## Project Structure

```
support/
  __init__.py
  app.py                  # Main wiring
  db.py                   # Base SQLite helpers
  models.py               # Ticket/binding data models
  cs_store.py             # Customer service persistent store
  model_router.py         # Multi-model LLM task routing
  telegram_gateway.py     # Telegram supergroup gateway (main entry)
  ai/
    backends.py           # LLM backend implementations
    rag.py                # RAG knowledge base
    router.py             # AI routing logic
  agents/
    pool.py               # Agent pool management
  analytics/
    metrics.py            # Metrics and reporting
  dashboard/
    api.py                # REST API + WebSocket server
    static/
      index.html          # Admin dashboard
      connect.html        # Connection management
      chat.html           # WebChat frontend
  infra/
    keyed_queue.py        # Per-key serialized async task queue
    health.py             # Channel health monitor + auto-reconnect
  tickets/
    identity.py           # Identity binding
    manager.py            # Ticket lifecycle
    escalation.py         # Escalation rules
knowledge/                # KB articles for RAG
tests/                    # Test suite
config.example.yaml       # Example configuration
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CS_TELEGRAM_TOKEN` | Yes | Telegram bot token |
| `CS_SUPPORT_GROUP_ID` | Yes | Telegram supergroup ID |
| `WEBCHAT_PORT` | No | WebChat HTTP port (default: 8081) |
| `WKIM_PORT` | No | WuKongIM compat port (default: 8080) |
| `MINIMAX_API_KEY` | No | MiniMax API key (translation + lang detect) |
| `DEEPSEEK_API_KEY` | No | DeepSeek API key (AI reply + summarize) |
| `OPENAI_API_KEY` | No | OpenAI API key (Whisper + fallback) |
| `CS_ROUTER_TRANSLATE` | No | Backend for translation (default: minimax) |
| `CS_ROUTER_AI_REPLY` | No | Backend for AI reply (default: deepseek) |

## License

MIT
