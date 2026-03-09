# AI Customer Support — Deployment, Configuration & API Guide

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Quick Start (5 minutes)](#quick-start)
- [Deployment Options](#deployment-options)
- [Configuration Reference](#configuration-reference)
- [Integration Methods](#integration-methods)
- [Agent Commands Reference](#agent-commands-reference)
- [API Reference](#api-reference)
- [Model Router Configuration](#model-router-configuration)
- [Security & Access Control](#security--access-control)
- [Infrastructure Components](#infrastructure-components)
- [Monitoring & Reports](#monitoring--reports)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
                    ┌──────────────────────────┐
                    │    Customer Channels      │
                    ├──────────┬───────┬────────┤
                    │ WebChat  │ WKIM  │  TG    │
                    │ (WS)     │ (HTTP)│(Direct)│
                    └────┬─────┴───┬───┴────┬───┘
                         │         │        │
                    ┌────▼─────────▼────────▼───┐
                    │   Telegram Gateway          │
                    │   (telegram_gateway.py)      │
                    │                              │
                    │  ┌─────────┐ ┌────────────┐ │
                    │  │ Keyed   │ │ Health     │ │
                    │  │ Queue   │ │ Monitor    │ │
                    │  └─────────┘ └────────────┘ │
                    └──────┬────────────┬──────────┘
                           │            │
              ┌────────────▼──┐   ┌─────▼──────────┐
              │ Telegram       │   │ Model Router   │
              │ Supergroup     │   │ (multi-LLM)    │
              │                │   │                │
              │ Topic 1: 用户A │   │ translate      │
              │ Topic 2: 用户B │   │ detect_lang    │
              │ Topic 3: 用户C │   │ ai_reply       │
              └────────────────┘   │ summarize      │
                                   └───────┬────────┘
                                           │
                    ┌──────────────────────────────────────┐
                    │ LLM Backends                         │
                    │ MiniMax │ DeepSeek │ Qwen │ OpenAI │ Claude │ GLM │
                    └──────────────────────────────────────┘
              ┌────────────────┐
              │ SQLite (cs_data.db)                       │
              │ sessions │ messages │ ratings │ tickets   │
              └────────────────┘
```

**Core workflow:**
1. Customer sends message via WebChat / WuKongIM App / Telegram
2. Gateway detects language, checks sensitive words, auto-translates
3. Message forwarded to Telegram supergroup as a Forum Topic (one topic per customer)
4. Agent replies in the topic thread → auto-translated back to customer's language
5. All messages persisted in SQLite with session/ticket tracking

---

## Prerequisites

| Item | Requirement |
|------|-------------|
| Python | 3.10+ |
| Telegram Bot | Create via [@BotFather](https://t.me/BotFather) |
| Telegram Supergroup | Forum mode enabled (Settings → Topics → ON) |
| Bot Permissions | Admin in supergroup (manage topics, send messages, ban users) |
| LLM API Key | At least one: MiniMax / DeepSeek / OpenAI (for translation + AI) |

### Create Telegram Bot

1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow prompts
3. Copy the token (e.g. `8654490446:AAHdSwBF4...`)
4. Enable inline mode: `/setinline` (optional, for future features)

### Create Telegram Supergroup

1. Create a new group in Telegram
2. Upgrade to Supergroup: Group Settings → convert
3. Enable Forum/Topics: Group Settings → Topics → ON
4. Add the bot as Admin (all permissions)
5. Get group ID: add [@RawDataBot](https://t.me/RawDataBot) to the group, it will print the chat ID (starts with `-100...`)
6. Remove @RawDataBot after getting the ID

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/gambletan/AI-Customer-Support.git
cd AI-Customer-Support

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e ".[all-channels]"

# 4. Configure (minimal)
cat > .env << 'EOF'
CS_TELEGRAM_TOKEN=your-bot-token-here
CS_SUPPORT_GROUP_ID=-100xxxxxxxxxx
MINIMAX_API_KEY=sk-your-minimax-key
EOF

# 5. Run
python -m support.telegram_gateway
# or: ai-cs (if installed via pip)
```

Startup log will show:
```
============================================================
Customer Service POC started! (full-featured)
  Web chat:    http://localhost:8081/chat
  WuKongIM:    http://localhost:8080
  Telegram:    group -100xxxxxxxxxx
  DB:          cs_data.db
  AI FAQ:      off
  Timeout:     180s
  Health:      every 30s
  Model Router:
    Backends: minimax
    translate: minimax (MiniMax-Text-01)
    detect_lang: minimax (MiniMax-Text-01)
    ai_reply: minimax (MiniMax-Text-01) [fallback from deepseek]
    summarize: minimax (MiniMax-Text-01) [fallback from deepseek]
============================================================
```

---

## Deployment Options

### Option 1: Direct Run (Development)

```bash
source .venv/bin/activate
python -m support.telegram_gateway
```

### Option 2: systemd Service (Linux Production)

```ini
# /etc/systemd/system/ai-cs.service
[Unit]
Description=AI Customer Support Gateway
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/AI-Customer-Support
EnvironmentFile=/opt/AI-Customer-Support/.env
ExecStart=/opt/AI-Customer-Support/.venv/bin/python -m support.telegram_gateway
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ai-cs
sudo systemctl start ai-cs
sudo journalctl -u ai-cs -f  # view logs
```

### Option 3: Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[all-channels]"
EXPOSE 8080 8081
CMD ["python", "-m", "support.telegram_gateway"]
```

```bash
docker build -t ai-cs .
docker run -d --name ai-cs --env-file .env -p 8080:8080 -p 8081:8081 ai-cs
```

### Option 4: Docker Compose

```yaml
# docker-compose.yml
version: "3.8"
services:
  ai-cs:
    build: .
    env_file: .env
    ports:
      - "8080:8080"
      - "8081:8081"
    volumes:
      - ./data:/app/data          # persist SQLite
      - ./knowledge:/app/knowledge # knowledge base
    restart: always
```

### Reverse Proxy (Nginx)

```nginx
# WebChat (port 8081)
server {
    listen 443 ssl;
    server_name cs.example.com;

    ssl_certificate     /etc/letsencrypt/live/cs.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cs.example.com/privkey.pem;

    # WebSocket for chat
    location /ws {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Chat page and static files
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Configuration Reference

All configuration via environment variables (or `.env` file).

### Core (Required)

| Variable | Description | Example |
|----------|-------------|---------|
| `CS_TELEGRAM_TOKEN` | Telegram bot token | `8654490446:AAHdSwBF4...` |
| `CS_SUPPORT_GROUP_ID` | Supergroup ID (with `-100` prefix) | `-1003753801101` |

### Ports & Networking

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBCHAT_PORT` | `8081` | WebChat HTTP/WS port |
| `WKIM_PORT` | `8080` | WuKongIM compatibility HTTP port |

### LLM API Keys

| Variable | Description |
|----------|-------------|
| `MINIMAX_API_KEY` | MiniMax API key (recommended primary) |
| `MINIMAX_BASE_URL` | Default: `https://api.minimaxi.com/v1` |
| `MINIMAX_MODEL` | Default: `MiniMax-Text-01` |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `DEEPSEEK_BASE_URL` | Default: `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | Default: `deepseek-chat` |
| `OPENAI_API_KEY` | OpenAI API key (also used for Whisper STT) |
| `OPENAI_BASE_URL` | Default: `https://api.openai.com/v1` |
| `OPENAI_MODEL` | Default: `gpt-4o-mini` |
| `QWEN_API_KEY` | Alibaba Qwen API key |
| `QWEN_MODEL` | Default: `qwen-plus` |
| `GLM_API_KEY` | Zhipu GLM API key |
| `GLM_MODEL` | Default: `glm-4-flash` |
| `CLAUDE_API_KEY` | Anthropic Claude API key |
| `CLAUDE_MODEL` | Default: `claude-sonnet-4-20250514` |

### Task Routing

| Variable | Default | Description |
|----------|---------|-------------|
| `CS_ROUTER_TRANSLATE` | `minimax` | Backend for translation |
| `CS_ROUTER_DETECT_LANG` | `minimax` | Backend for language detection |
| `CS_ROUTER_AI_REPLY` | `deepseek` | Backend for AI auto-reply |
| `CS_ROUTER_SUMMARIZE` | `deepseek` | Backend for summarization/reports |

### Agent Management

| Variable | Default | Description |
|----------|---------|-------------|
| `CS_AGENTS` | (empty) | Comma-separated agent names. Empty = auto-assign off |
| `CS_ALLOWED_AGENTS` | (empty) | Comma-separated Telegram user IDs. Empty = open mode |
| `CS_MAX_SESSIONS_PER_AGENT` | `5` | Max concurrent sessions per agent |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `CS_AI_ENABLED` | `false` | Enable AI auto-reply (FAQ + LLM) |
| `CS_REPLY_TIMEOUT` | `180` | Seconds before timeout alert (0 = off) |
| `CS_DB_PATH` | `cs_data.db` | SQLite database path |
| `CS_HEALTH_INTERVAL` | `30` | Health check interval in seconds |

### Complete `.env` Example

```bash
# === Required ===
CS_TELEGRAM_TOKEN=8654490446:AAHdSwBF4C0M7jXiN23YMmQJVUjwodb8IxM
CS_SUPPORT_GROUP_ID=-1003753801101

# === Ports ===
WEBCHAT_PORT=8081
WKIM_PORT=8080

# === LLM (at least one) ===
MINIMAX_API_KEY=sk-cp-xxxxxxxxxxxxxxxxxxxxxxxx
MINIMAX_BASE_URL=https://api.minimaxi.com/v1
MINIMAX_MODEL=MiniMax-Text-01

DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx

# === Task Routing ===
CS_ROUTER_TRANSLATE=minimax
CS_ROUTER_DETECT_LANG=minimax
CS_ROUTER_AI_REPLY=deepseek
CS_ROUTER_SUMMARIZE=deepseek

# === Agents ===
CS_AGENTS=alice,bob,charlie
CS_ALLOWED_AGENTS=123456789,987654321
CS_MAX_SESSIONS_PER_AGENT=5

# === Features ===
CS_AI_ENABLED=true
CS_REPLY_TIMEOUT=180
CS_DB_PATH=cs_data.db
CS_HEALTH_INTERVAL=30
```

---

## Integration Methods

The system provides **4 ways** to connect customers:

### 1. WebChat (WebSocket) — Embed in any website

**URL:** `http://your-server:8081/chat`

#### Embed as iframe

```html
<iframe
  src="https://cs.example.com/chat"
  width="420"
  height="680"
  style="border: none; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.12);"
></iframe>
```

#### Embed with user identity (URL params)

```html
<!-- Pass logged-in user info via URL params -->
<iframe src="https://cs.example.com/chat?user_id=C10086&name=张三&phone=13800138000"></iframe>
```

#### Embed with user identity (JS API)

```html
<script>
  // Set before iframe loads
  window.CHAT_USER = {
    user_id: "C10086",
    name: "张三",
    phone: "13800138000"
  };
</script>
<iframe src="https://cs.example.com/chat"></iframe>
```

#### Embed with user identity (postMessage)

```javascript
// Send user info to chat iframe at any time
const chatFrame = document.getElementById('chatFrame');
chatFrame.contentWindow.postMessage({
  type: 'chat_user',
  user_id: 'C10086',
  name: '张三',
  phone: '13800138000',
  extra: { vip: true, order_count: 12 }
}, '*');
```

#### Direct WebSocket API

```javascript
// Connect directly via WebSocket
const ws = new WebSocket('wss://cs.example.com/ws?user_id=C10086&name=张三');

// Send text message
ws.send(JSON.stringify({ type: 'text', text: 'Hello, I need help' }));

// Send image/video
ws.send(JSON.stringify({
  type: 'media',
  media_type: 'image',  // or 'video'
  data: 'data:image/jpeg;base64,/9j/4AAQ...',
  text: 'See this screenshot'
}));

// Send callback (e.g. rating)
ws.send(JSON.stringify({
  type: 'callback',
  callback_data: 'rate:session123:5'
}));

// Receive messages
ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  // data.type: 'system' | 'text' | 'media' | 'typing' | 'history'
  console.log(data);
};
```

**WebSocket Message Types (server → client):**

| type | Fields | Description |
|------|--------|-------------|
| `system` | `text`, `session_id`, `user_type` | Connection status, session info |
| `text` | `text`, `buttons?` | Agent text reply (optional inline buttons) |
| `media` | `url`, `text`, `media_type` | Image/video/document from agent |
| `typing` | — | Agent is typing indicator |
| `history` | `messages[]` | Unseen message history on reconnect |
| `unseen_notice` | `count` | Number of unseen messages |

### 2. WuKongIM-Compatible HTTP API — For existing mobile apps

**Base URL:** `http://your-server:8080`

Compatible with WuKongIM client SDK, allowing existing Android/iOS apps to connect without code changes.

```bash
# Send message
curl -X POST http://localhost:8080/api/message/send \
  -H "Content-Type: application/json" \
  -d '{
    "from_uid": "user_123",
    "to_uid": "cs_bot",
    "content": "I need help with my order"
  }'

# Get history
curl http://localhost:8080/api/message/history?uid=user_123&limit=50
```

### 3. Telegram Direct — Customers message bot directly

Customers can also message the bot on Telegram directly. Their messages are routed to the support group as topics, same as WebChat/WKIM users.

### 4. REST API — For backend/ERP integration

Build custom integrations by calling the internal API:

```python
import httpx

# Example: create a support session from your backend
async def create_support_session(user_id: str, user_name: str, issue: str):
    async with httpx.AsyncClient() as client:
        # Connect via WebSocket and send initial message
        # Or post to WuKongIM-compatible endpoint
        resp = await client.post("http://localhost:8080/api/message/send", json={
            "from_uid": user_id,
            "to_uid": "cs_bot",
            "content": issue,
            "extra": {
                "user_name": user_name,
                "source": "erp_system"
            }
        })
```

---

## Agent Commands Reference

Agents reply in the Telegram supergroup topic threads. Available commands:

### Query Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/erp [ID]` | Query ERP user info | `/erp C10086` |
| `/order [phone/ID]` | Query orders | `/order 13800138000` |
| `/history [N]` | View last N messages | `/history 30` |
| `/lang` | Check user language + translation status | `/lang` |

### Action Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/tpl [name]` | Send quick reply template (list all if no name) | `/tpl 欢迎` |
| `/ticket title` | Create a ticket | `/ticket 退款问题` |
| `/transfer agent` | Transfer session to another agent | `/transfer bob` |
| `/close` | Close session + send satisfaction survey | `/close` |
| `/queue` | View waiting queue | `/queue` |

### Report Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/report [date]` | Daily statistics report | `/report 2026-03-09` |
| `/hotwords [days]` | Hot keyword analysis | `/hotwords 7` |
| `/help` | Show all commands | `/help` |

### Quick Reply Templates (built-in)

| Name | Text |
|------|------|
| `欢迎` | 您好！很高兴为您服务，请问有什么可以帮您？ |
| `稍等` | 好的，请您稍等，我帮您查一下。 |
| `发货` | 您的订单已发货，物流单号为 xxxxxx，请注意查收。 |
| `退款` | 退款申请已提交，预计1-3个工作日到账，请耐心等待。 |
| `感谢` | 感谢您的耐心等待，还有其他需要帮助的吗？ |
| `结束` | 感谢您的咨询，祝您生活愉快！如有需要随时联系我们。 |

Templates are auto-translated to the user's detected language.

---

## API Reference

### WebSocket Protocol (`/ws`)

**Connection:**
```
ws://host:8081/ws
ws://host:8081/ws?user_id=C10086&name=张三&phone=13800138000
ws://host:8081/ws?session_id=abc123   (resume anonymous session)
```

**Client → Server Messages:**

```jsonc
// Text message
{ "type": "text", "text": "Hello" }

// Media (base64 data URL)
{
  "type": "media",
  "media_type": "image",       // "image" | "video"
  "data": "data:image/jpeg;base64,...",
  "text": "optional caption"
}

// Auth (mid-session identity binding)
{
  "type": "auth",
  "user_id": "C10086",
  "name": "张三",
  "phone": "13800138000"
}

// Callback (e.g. rating buttons)
{ "type": "callback", "callback_data": "rate:session_id:5" }
```

**Server → Client Messages:**

```jsonc
// Connection established
{
  "type": "system",
  "text": "connected",
  "session_id": "abc123-def456",
  "user_type": "anonymous"     // or "authenticated"
}

// Agent reply
{ "type": "text", "text": "Hello, how can I help?" }

// Agent reply with buttons (e.g. rating)
{
  "type": "text",
  "text": "Please rate our service:",
  "buttons": [[
    { "label": "⭐", "callback_data": "rate:sid:1" },
    { "label": "⭐⭐", "callback_data": "rate:sid:2" },
    { "label": "⭐⭐⭐⭐⭐", "callback_data": "rate:sid:5" }
  ]]
}

// Media from agent
{
  "type": "media",
  "url": "https://api.telegram.org/file/bot.../photo.jpg",
  "text": "Here is the screenshot",
  "media_type": "image"
}

// Typing indicator
{ "type": "typing" }

// History (on reconnect)
{
  "type": "history",
  "messages": [
    { "sender": "user", "text": "Hi", "timestamp": "2026-03-09 10:00:00" },
    { "sender": "agent", "text": "Hello!", "timestamp": "2026-03-09 10:01:00" }
  ]
}

// Unseen message count
{ "type": "unseen_notice", "count": 3 }
```

### Database Schema

```sql
-- Session tracking
sessions (
    session_id TEXT PRIMARY KEY,
    topic_id INTEGER,           -- Telegram forum topic ID
    channel TEXT,               -- 'webchat' | 'wkim' | 'telegram'
    user_type TEXT,             -- 'anonymous' | 'authenticated'
    user_id TEXT,
    user_name TEXT,
    user_phone TEXT,
    user_extra TEXT,            -- JSON
    user_lang TEXT,             -- ISO 639-1 ('zh', 'en', 'fr', etc.)
    assigned_agent TEXT,
    status TEXT,                -- 'active' | 'closed'
    first_reply_at TEXT,
    last_seen_msg_id INTEGER,
    created_at TEXT,
    updated_at TEXT,
    closed_at TEXT
)

-- Message history
messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    sender TEXT,                -- 'user' | 'agent'
    content TEXT,
    media_url TEXT,
    media_type TEXT,            -- 'image' | 'video' | 'document'
    timestamp TEXT
)

-- Satisfaction ratings
ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    score INTEGER,              -- 1-5
    comment TEXT,
    created_at TEXT
)

-- Tickets
tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    title TEXT,
    status TEXT,                -- 'open' | 'closed'
    created_by TEXT,
    created_at TEXT
)

-- Sensitive word detection log
sensitive_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    original_text TEXT,
    matched_words TEXT,
    timestamp TEXT
)
```

---

## Model Router Configuration

The Model Router routes different tasks to different LLM backends with automatic fallback.

### Task Types

| Task | Description | Default Backend |
|------|-------------|-----------------|
| `translate` | Bidirectional translation between user language and Chinese | `minimax` |
| `detect_lang` | Detect user's language (Latin scripts: fr, es, de, etc.) | `minimax` |
| `ai_reply` | AI auto-reply for FAQ and common questions | `deepseek` |
| `summarize` | Session summarization, daily reports | `deepseek` |

### Fallback Chain

If the configured backend is unavailable (no API key), it falls back in this order:
```
configured → minimax → openai → deepseek → qwen → glm → claude
```

### Example: MiniMax for translation, DeepSeek for AI reply

```bash
MINIMAX_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx
CS_ROUTER_TRANSLATE=minimax
CS_ROUTER_DETECT_LANG=minimax
CS_ROUTER_AI_REPLY=deepseek
CS_ROUTER_SUMMARIZE=deepseek
```

### Example: All tasks via OpenAI

```bash
OPENAI_API_KEY=sk-xxx
CS_ROUTER_TRANSLATE=openai
CS_ROUTER_DETECT_LANG=openai
CS_ROUTER_AI_REPLY=openai
CS_ROUTER_SUMMARIZE=openai
```

### Programmatic Usage

```python
from support.model_router import ModelRouter

router = ModelRouter.from_env()

# Translate
result = await router.chat("translate", [
    {"role": "system", "content": "Translate to English. Only output the translation."},
    {"role": "user", "content": "你好世界"},
])
# → "Hello World"

# Detect language
lang = await router.chat("detect_lang", [
    {"role": "system", "content": "Detect language. Reply with ISO 639-1 code only."},
    {"role": "user", "content": "Bonjour le monde"},
], temperature=0, max_tokens=5)
# → "fr"

# AI reply
reply = await router.chat("ai_reply", messages, temperature=0.3, max_tokens=300)

# Check which backends are available
for line in router.summary():
    print(line)
```

---

## Security & Access Control

### Telegram Group Access Control

Restrict who can be an agent in the support group:

```bash
# Only these Telegram user IDs can access the support group
# Get user IDs: message @userinfobot on Telegram
CS_ALLOWED_AGENTS=123456789,987654321

# Empty = open mode (anyone in the group can reply)
CS_ALLOWED_AGENTS=
```

**Behavior when enabled:**
- Unauthorized users joining the group are automatically kicked (ban + unban)
- Messages from unauthorized users in the group are silently ignored
- Bot's own messages are always allowed

### Sensitive Word Filtering

Add sensitive words in `telegram_gateway.py`:

```python
SENSITIVE_WORDS = [
    "投诉", "举报", "律师", "法院",
    "complaint", "lawyer", "sue",
]
```

When detected:
- Agent receives `⚠️ 敏感词检测: xxx` warning in the topic
- Message is still forwarded (not blocked)
- Detection is logged in the `sensitive_log` table

### Anonymous vs Authenticated Users

| Feature | Anonymous | Authenticated |
|---------|-----------|---------------|
| Topic name | `💬 访客_abc123` | `👤 张三` |
| ERP lookup | Not available | `/erp` shows full info |
| Session resume | By `session_id` cookie | By `user_id` (cross-device) |
| Order query | Requires manual input | Auto-linked |

---

## Infrastructure Components

### Keyed Async Queue

Ensures messages from the same customer are processed one at a time (FIFO), while messages from different customers run concurrently.

```python
from support.infra.keyed_queue import KeyedAsyncQueue

queue = KeyedAsyncQueue()

# These run in parallel (different keys)
await queue.run("customer_A", process(msg_a))
await queue.run("customer_B", process(msg_b))

# These run serially (same key)
await queue.run("customer_A", process(msg_a1))
await queue.run("customer_A", process(msg_a2))
```

- Locks are created on-demand and auto-cleaned when idle
- Error handling with optional callback

### Health Monitor

Auto-detects stale connections and reconnects with exponential backoff.

```python
from support.infra.health import HealthMonitor

monitor = HealthMonitor(interval=30)  # check every 30s
await monitor.start(channel_manager)

# Backoff: 30s → 60s → 120s → 240s → 300s (max)
# Resets to 30s after successful recovery
```

Configure via env:
```bash
CS_HEALTH_INTERVAL=30  # seconds between health checks
```

---

## Monitoring & Reports

### Daily Report (`/report`)

Automatically aggregated from SQLite:

```
📊 日报 2026-03-09

• 总会话: 42
• 已关闭: 38
• 总消息: 267
• 平均评分: 4.3
• 平均首次响应: 45s

👥 客服工作量:
  • alice: 15会话 / 89回复
  • bob: 12会话 / 67回复
  • charlie: 15会话 / 78回复
```

### Hot Keywords (`/hotwords`)

Analyzes user messages to identify trending topics:

```
🔥 近 7 天热词 Top 10:

1. 退款 (23次)
2. 发货 (18次)
3. 订单 (15次)
...
```

### Queue Status (`/queue`)

Real-time waiting queue when all agents are at capacity:

```
📋 排队用户 (3):
1. 张三 (`abc123…`)
2. 访客 (`def456…`)
3. 李四 (`ghi789…`)
```

### Satisfaction Ratings

After `/close`, users receive a 1-5 star rating prompt. Results stored in `ratings` table and included in daily reports.

---

## Troubleshooting

### Bot not receiving messages

1. Check bot is admin in the supergroup
2. Ensure forum/topics mode is enabled
3. Verify `CS_SUPPORT_GROUP_ID` starts with `-100`
4. Check bot privacy mode: message @BotFather → `/setprivacy` → Disable

### Translation not working

1. Check at least one LLM API key is configured
2. Verify with logs: look for `translation failed` or `language detection API failed`
3. Test manually:
   ```bash
   curl https://api.minimaxi.com/v1/chat/completions \
     -H "Authorization: Bearer $MINIMAX_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"MiniMax-Text-01","messages":[{"role":"user","content":"Translate to Chinese: Hello"}]}'
   ```

### WebSocket connection drops

- Check firewall allows the port
- If behind nginx, ensure `proxy_read_timeout` is long enough (86400 for websocket)
- Health monitor will auto-reconnect Telegram channel; WebSocket clients auto-reconnect every 3s

### Forum topic creation fails

- Bot needs "Manage Topics" permission in the supergroup
- Supergroup must have Topics/Forum mode enabled
- Check Telegram API errors in logs

### High memory usage

- SQLite WAL mode is enabled by default for better concurrent performance
- For very high volume, consider periodic cleanup of old closed sessions
- Queue locks are auto-cleaned when idle

### Database locked errors

- Only one instance should run against the same `cs_data.db`
- Use separate DB paths for separate instances
- WAL mode already reduces lock contention

### Agent commands not working

- Commands must be sent inside a topic thread (not the general chat)
- Bot must have permission to send messages in the group
- Check `CS_ALLOWED_AGENTS` if access control is enabled
