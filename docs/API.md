# Unified Support API Reference

Base URL: `http://localhost:8081`

## Architecture

```
Browser/App ──WebSocket──→ WebChat Adapter ──→ ChannelManager ──→ AI / Agent
                                                     ↑
Telegram/WeChat/... ──→ IM Adapters ────────────────┘
                                                     ↓
Dashboard (Agent UI) ←── REST + WebSocket ←── DashboardAPI
```

The system exposes two independent servers:

| Server | Default Port | Purpose |
|--------|-------------|---------|
| **WebChat** | 8081 `/ws` | Customer-facing WebSocket chat |
| **Dashboard** | 8081 `/api/*` | Agent-facing REST + WebSocket |

> In production, separate ports via config. Both default to 8081 for the POC.

---

## 1. WebChat (Customer-Facing)

WebSocket endpoint for anonymous or authenticated browser chat.

### Connect

```
ws://HOST:PORT/ws
ws://HOST:PORT/ws?user_id=C10086&name=张三&phone=138xxxx
```

| Query Param | Required | Description |
|-------------|----------|-------------|
| `user_id` | No | Platform user ID (authenticated mode) |
| `name` | No | Display name |
| `phone` | No | Phone number |

On connect, server sends:

```json
{
  "type": "system",
  "text": "connected",
  "session_id": "abc123def456",
  "user_type": "anonymous"
}
```

### Wire Protocol (JSON over WebSocket)

#### Client → Server

**Send text message:**

```json
{ "type": "text", "text": "How do I reset my password?" }
```

**Send media (base64):**

```json
{
  "type": "media",
  "media_type": "image",
  "data": "data:image/png;base64,iVBOR...",
  "text": "Here is my screenshot"
}
```

**Upgrade to authenticated user (optional, post-connect):**

```json
{
  "type": "auth",
  "user_id": "C10086",
  "name": "张三",
  "phone": "138xxxx",
  "extra": { "vip_level": 3 }
}
```

Server responds:

```json
{ "type": "system", "text": "authenticated", "user_type": "authenticated" }
```

#### Server → Client

**Text reply:**

```json
{
  "type": "text",
  "text": "To reset your password, go to Settings > Security > Reset Password.",
  "id": "a1b2c3d4",
  "timestamp": "2026-03-09T14:30:00.000000"
}
```

**Media reply:**

```json
{
  "type": "media",
  "media_type": "image",
  "url": "https://cdn.example.com/guide.png",
  "text": "Follow this guide",
  "id": "e5f6g7h8",
  "timestamp": "2026-03-09T14:30:05.000000"
}
```

### Health Check

```
GET /health
```

```json
{ "status": "ok", "sessions": 3 }
```

---

## 2. Dashboard API (Agent-Facing)

REST endpoints for the agent dashboard. All responses are JSON.

### 2.1 Tickets

#### List tickets

```
GET /api/tickets?status=open&channel=telegram&limit=50&offset=0
```

| Query Param | Required | Values |
|-------------|----------|--------|
| `status` | No | `open`, `escalated`, `assigned`, `resolved`, `closed` |
| `channel` | No | `telegram`, `webchat`, `whatsapp`, `wechat`, `line`, etc. |
| `limit` | No | Default `50` |
| `offset` | No | Default `0` |

**Response** `200`:

```json
[
  {
    "id": "a1b2c3d4e5f6",
    "channel": "telegram",
    "customer_name": "张三",
    "subject": "Password reset",
    "status": "open",
    "priority": "normal",
    "assigned_agent_id": null,
    "created_at": "2026-03-09T10:00:00+00:00",
    "updated_at": "2026-03-09T10:05:00+00:00"
  }
]
```

#### Get ticket detail

```
GET /api/tickets/{id}
```

**Response** `200`:

```json
{
  "id": "a1b2c3d4e5f6",
  "channel": "telegram",
  "chat_id": "123456789",
  "customer_id": "C10086",
  "customer_name": "张三",
  "subject": "Password reset",
  "status": "escalated",
  "priority": "high",
  "assigned_agent_id": "agent-1",
  "language": "zh",
  "created_at": "2026-03-09T10:00:00+00:00",
  "updated_at": "2026-03-09T10:15:00+00:00",
  "resolved_at": null
}
```

**Response** `404`:

```json
{ "error": "not found" }
```

#### Get ticket messages

```
GET /api/tickets/{id}/messages
```

**Response** `200`:

```json
[
  {
    "id": 1,
    "role": "customer",
    "sender_name": "张三",
    "content": "I can't reset my password",
    "channel": "telegram",
    "created_at": "2026-03-09T10:00:00+00:00"
  },
  {
    "id": 2,
    "role": "ai",
    "sender_name": null,
    "content": "Please go to Settings > Security...",
    "channel": null,
    "created_at": "2026-03-09T10:00:02+00:00"
  },
  {
    "id": 3,
    "role": "agent",
    "sender_name": null,
    "content": "Let me check your account directly.",
    "channel": null,
    "created_at": "2026-03-09T10:10:00+00:00"
  }
]
```

Message roles: `customer` | `ai` | `agent`

#### Reply to ticket (as agent)

```
POST /api/tickets/{id}/reply
Content-Type: application/json

{ "text": "I've reset your password. Please check your email." }
```

**Response** `200`:

```json
{ "ok": true }
```

The reply is sent to the customer via their original IM channel and stored in message history.

#### Resolve ticket

```
POST /api/tickets/{id}/resolve
```

**Response** `200`:

```json
{ "ok": true }
```

Sets ticket status to `resolved` and sends a resolution message to the customer.

### 2.2 Agents

#### List agents

```
GET /api/agents
```

**Response** `200`:

```json
[
  {
    "id": "agent-1",
    "name": "Support Team",
    "status": "online",
    "current_load": 2,
    "max_concurrent": 5,
    "channel": "telegram"
  }
]
```

Agent statuses: `online` | `offline` | `busy`

### 2.3 Analytics

#### Get summary

```
GET /api/analytics
```

Returns aggregate stats (ticket counts, response times, CSAT scores, etc.).

### 2.4 Customer Identity Binding

Enables "scan QR code with your own IM" flow. Your platform generates personalized links; when the customer clicks/scans, their IM account gets bound to their platform user ID.

#### Get connect links

```
GET /api/connect-links/{uid}?tg_bot=MyBot&wa_number=1234567890&line_id=@myline
```

| Path Param | Description |
|-----------|-------------|
| `uid` | Your platform's user ID |

| Query Param | Description |
|-------------|-------------|
| `tg_bot` | Telegram bot username |
| `wa_number` | WhatsApp business number |
| `line_id` | LINE Official Account ID |

**Response** `200`:

```json
{
  "uid": "USER123",
  "links": {
    "telegram": "https://t.me/MyBot?start=uid_USER123",
    "whatsapp": "https://wa.me/1234567890?text=uid_USER123",
    "line": "https://line.me/R/oaMessage/@myline/?uid_USER123",
    "universal": "/connect.html?uid=USER123"
  }
}
```

Each link can be rendered as a QR code on your web/app. When the customer scans with their IM app, the `IdentityMiddleware` auto-binds the IM identity to the platform user.

**Binding flow:**

```
Your App                    IM (Telegram/WeChat/...)         Support System
  │                                │                              │
  ├─ GET /api/connect-links/U123   │                              │
  │◄─ { telegram: "t.me/...?start=uid_U123" }                    │
  │                                │                              │
  ├─ Show QR code to user ────────►│                              │
  │                                ├─ /start uid_U123 ──────────►│
  │                                │                    IdentityMiddleware
  │                                │                    binds telegram:9876 → U123
  │                                │◄─ "Welcome! Account linked." │
  │                                │                              │
  │                                ├─ "I need help with..." ────►│
  │                                │              (tagged as U123) │
```

#### Get user bindings

```
GET /api/user/{uid}/bindings
```

**Response** `200`:

```json
[
  {
    "channel": "telegram",
    "chat_id": "987654321",
    "bound_at": "2026-03-09T08:00:00+00:00"
  },
  {
    "channel": "whatsapp",
    "chat_id": "8613800138000",
    "bound_at": "2026-03-09T09:30:00+00:00"
  }
]
```

### 2.5 WebSocket (Real-time Events)

```
ws://HOST:PORT/ws
```

> Note: This is the **dashboard** WebSocket, separate from the WebChat `/ws`. In production, use different ports.

Server pushes events as JSON:

**New message on a ticket:**

```json
{ "type": "message", "ticket_id": "a1b2c3d4e5f6" }
```

**Ticket resolved:**

```json
{ "type": "resolved", "ticket_id": "a1b2c3d4e5f6" }
```

---

## 3. Identity Binding Patterns

The `IdentityMiddleware` recognizes these patterns in incoming messages to auto-bind:

| Pattern | Example | Source |
|---------|---------|--------|
| `/start uid_XXX` | `/start uid_USER123` | Telegram deep link |
| `/start XXX` | `/start USER123` | Telegram (any payload) |
| `uid_XXX` / `uid:XXX` / `uid=XXX` | `uid_USER123` | WhatsApp / LINE first message |
| `bind XXX` | `bind USER123` | Explicit bind command |

---

## 4. Data Models

### Ticket

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | 12-char hex ID |
| `channel` | string | Source channel |
| `chat_id` | string | Channel-specific conversation ID |
| `customer_id` | string | Platform user ID (if bound) |
| `customer_name` | string? | Display name |
| `subject` | string? | Auto-extracted topic |
| `status` | enum | `open` → `escalated` → `assigned` → `resolved` → `closed` |
| `priority` | enum | `low`, `normal`, `high`, `urgent` |
| `assigned_agent_id` | string? | Assigned human agent |
| `language` | string? | Detected language |
| `created_at` | ISO 8601 | |
| `updated_at` | ISO 8601 | |
| `resolved_at` | ISO 8601? | |

### Ticket lifecycle

```
Customer sends message
        ↓
   [TicketMiddleware] creates ticket (status: open)
        ↓
   [AI Router] auto-replies (up to max_ai_turns)
        ↓
   AI cannot resolve / customer requests human
        ↓
   [EscalationMiddleware] escalates (status: escalated)
        ↓
   Agent assigned (status: assigned)
        ↓
   Agent resolves via dashboard (status: resolved)
```

### Agent

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Agent identifier |
| `name` | string | Display name |
| `status` | enum | `online`, `offline`, `busy` |
| `channel` | string? | Agent's IM channel for notifications |
| `chat_id` | string? | Agent's chat ID on that channel |
| `max_concurrent` | int | Max concurrent tickets (default 5) |
| `current_load` | int | Currently assigned tickets |
| `skills` | string[] | Skill tags, e.g. `["billing", "tech"]` |

### CustomerBinding

| Field | Type | Description |
|-------|------|-------------|
| `platform_user_id` | string | Your platform's user ID |
| `channel` | string | IM channel name |
| `chat_id` | string | Channel-specific user/chat ID |
| `bound_at` | ISO 8601 | When the binding was created |

---

## 5. Sample Code

### 5.1 WebChat — Minimal Browser Client (JavaScript)

```html
<script>
// Connect as authenticated user (or omit params for anonymous)
const ws = new WebSocket('ws://localhost:8081/ws?user_id=C10086&name=张三');
let sessionId = null;

ws.onmessage = (e) => {
  const data = JSON.parse(e.data);

  switch (data.type) {
    case 'system':
      sessionId = data.session_id;
      console.log(`Connected: ${data.user_type} session=${sessionId}`);
      break;

    case 'text':
      appendMessage('agent', data.text);
      break;

    case 'media':
      appendMedia(data.media_type, data.url, data.text);
      break;

    case 'history':
      // Reconnect: server sends previous messages
      data.messages.forEach(m => {
        appendMessage(m.sender === 'user' ? 'user' : 'agent', m.text);
      });
      break;
  }
};

// Send text
function send(text) {
  ws.send(JSON.stringify({ type: 'text', text }));
  appendMessage('user', text);
}

// Send image from <input type="file">
function sendImage(file) {
  const reader = new FileReader();
  reader.onload = () => {
    ws.send(JSON.stringify({
      type: 'media',
      media_type: file.type.startsWith('video') ? 'video' : 'image',
      data: reader.result,
      text: '',
    }));
  };
  reader.readAsDataURL(file);
}

// Upgrade anonymous → authenticated (post-connect)
function authenticate(userId, name) {
  ws.send(JSON.stringify({ type: 'auth', user_id: userId, name }));
}

// Rating callback (after /close)
function submitRating(callbackData) {
  ws.send(JSON.stringify({ type: 'callback', callback_data: callbackData }));
}
</script>
```

### 5.2 Embed Chat Widget in Your App

**Option A: iframe with URL params**

```html
<iframe
  src="http://localhost:8081/chat?user_id=C10086&name=张三&phone=138xxxx"
  style="width: 420px; height: 680px; border: none; border-radius: 16px;"
></iframe>
```

**Option B: postMessage for SPAs (pass identity after login)**

```javascript
// In your app — after user logs in
const iframe = document.getElementById('chatFrame');
iframe.contentWindow.postMessage({
  type: 'chat_user',
  user_id: currentUser.id,
  name: currentUser.name,
  phone: currentUser.phone,
  extra: { vip_level: 3 },
}, '*');
```

**Option C: Set global before chat widget loads**

```html
<script>
  window.CHAT_USER = { user_id: 'C10086', name: '张三', phone: '138xxxx' };
</script>
<script src="customer_service_chat.html"></script>
```

### 5.3 Dashboard REST API — Ticket Operations (Python)

```python
import httpx

BASE = "http://localhost:8081"

async def main():
    async with httpx.AsyncClient() as c:
        # List open tickets
        r = await c.get(f"{BASE}/api/tickets", params={"status": "open"})
        tickets = r.json()
        print(f"Open tickets: {len(tickets)}")

        if not tickets:
            return
        tid = tickets[0]["id"]

        # Get conversation history
        r = await c.get(f"{BASE}/api/tickets/{tid}/messages")
        for msg in r.json():
            print(f"  [{msg['role']}] {msg['content']}")

        # Agent replies (sends to customer via their original IM channel)
        await c.post(f"{BASE}/api/tickets/{tid}/reply", json={
            "text": "Hi, I've checked your account. Your issue has been fixed."
        })

        # Resolve ticket (sends resolution message + triggers CSAT)
        await c.post(f"{BASE}/api/tickets/{tid}/resolve")

import asyncio
asyncio.run(main())
```

### 5.4 Dashboard REST API — Ticket Operations (JavaScript)

```javascript
const BASE = 'http://localhost:8081';

// List escalated tickets
const tickets = await fetch(`${BASE}/api/tickets?status=escalated`).then(r => r.json());

// Get messages
const messages = await fetch(`${BASE}/api/tickets/${tickets[0].id}/messages`).then(r => r.json());

// Reply
await fetch(`${BASE}/api/tickets/${tickets[0].id}/reply`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text: 'We are looking into this.' }),
});

// Resolve
await fetch(`${BASE}/api/tickets/${tickets[0].id}/resolve`, { method: 'POST' });
```

### 5.5 Real-time Dashboard (WebSocket)

```javascript
// Dashboard WebSocket — receives ticket lifecycle events
const ws = new WebSocket('ws://localhost:8081/ws');

ws.onmessage = (e) => {
  const event = JSON.parse(e.data);

  switch (event.type) {
    case 'message':
      // New message on ticket — refresh chat view
      refreshMessages(event.ticket_id);
      break;
    case 'resolved':
      // Ticket resolved — update list
      refreshTicketList();
      break;
  }
};
```

### 5.6 QR Code Identity Binding

Generate personalized deep links so users can scan a QR code with their IM app to connect.

**Step 1: Get connect links for a platform user**

```python
import httpx
import qrcode  # pip install qrcode[pil]

async def generate_qr_codes(user_id: str, tg_bot: str = "MyServiceBot"):
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"http://localhost:8081/api/connect-links/{user_id}",
            params={"tg_bot": tg_bot, "wa_number": "8613800001111"},
        )
        links = r.json()["links"]

    # Generate QR code images
    for channel, url in links.items():
        if channel == "universal":
            continue
        qr = qrcode.make(url)
        qr.save(f"qr_{channel}_{user_id}.png")
        print(f"{channel}: {url}")

    # Result:
    # telegram: https://t.me/MyServiceBot?start=uid_U123
    # whatsapp: https://wa.me/8613800001111?text=uid_U123
```

**Step 2: Show QR codes in frontend**

```html
<div id="connect-channels"></div>
<script src="https://cdn.jsdelivr.net/npm/qrcodejs/qrcode.min.js"></script>
<script>
async function showConnectQR(userId) {
  const r = await fetch(`/api/connect-links/${userId}?tg_bot=MyServiceBot`);
  const { links } = await r.json();
  const container = document.getElementById('connect-channels');

  for (const [channel, url] of Object.entries(links)) {
    if (channel === 'universal') continue;
    const div = document.createElement('div');
    div.innerHTML = `<h3>${channel}</h3>`;
    container.appendChild(div);
    new QRCode(div, { text: url, width: 200, height: 200 });
  }
}
showConnectQR('USER123');
</script>
```

**Step 3: Check user's bound channels**

```python
# After user scans QR and connects via IM, check what's bound:
r = await c.get(f"{BASE}/api/user/USER123/bindings")
# [{"channel": "telegram", "chat_id": "987654321", "bound_at": "..."},
#  {"channel": "whatsapp", "chat_id": "8613800138000", "bound_at": "..."}]
```

### 5.7 Python — Build Your Own Support Server

```python
"""Minimal support server using unified-channel + unified-support."""
import asyncio
from unified_channel import ChannelManager, TelegramAdapter
from unified_channel.adapters.webchat import WebChatAdapter

from support.ai.backends import create_backend
from support.ai.rag import KnowledgeBase
from support.ai.router import AIRouter
from support.dashboard.api import DashboardAPI
from support.db import Database
from support.tickets.manager import TicketMiddleware
from support.tickets.escalation import EscalationMiddleware
from support.tickets.identity import IdentityMiddleware
from support.analytics.metrics import Analytics

async def main():
    # Database
    db = Database("support.db")
    await db.connect()

    # AI (RAG over knowledge base)
    llm = create_backend(backend_name="deepseek", api_key="sk-xxx", model="deepseek-chat")
    kb = KnowledgeBase(db, "knowledge")
    await kb.reindex()
    ai = AIRouter(llm=llm, kb=kb)

    # Channels
    manager = ChannelManager()
    manager.add_channel(WebChatAdapter(port=8080))       # Browser customers
    manager.add_channel(TelegramAdapter(token="TOKEN"))   # Telegram customers

    # Middleware pipeline (order matters)
    manager.add_middleware(IdentityMiddleware(db))         # QR bind: IM → platform user
    manager.add_middleware(TicketMiddleware(db))            # Auto-create tickets
    manager.add_middleware(EscalationMiddleware(db, ai, send_fn=manager.send))

    # Default handler — AI auto-reply
    @manager.on_message
    async def handle(msg):
        history = (msg.metadata or {}).get("history", [])
        formatted = [{"role": h["role"], "content": h["content"]} for h in history[-10:]]
        return await ai.generate_reply(msg.content.text or "", formatted)

    # Agent dashboard
    dashboard = DashboardAPI(db=db, analytics=Analytics(db), send_fn=manager.send, port=8081)
    await dashboard.start()

    try:
        await manager.run()
    finally:
        await dashboard.stop()
        await db.close()

asyncio.run(main())
```

### 5.8 POC — Quick Start (Telegram Group + WebChat)

The POC (`examples/customer_service_poc.py`) is a standalone full-featured system. No unified-support needed.

```bash
cd unified-channel

# Configure
cat > examples/.env << 'EOF'
TELEGRAM_TOKEN=your-bot-token
SUPPORT_GROUP_ID=-100xxxxxxxxxx

# AI auto-reply (optional)
CS_AI_ENABLED=true
DEEPSEEK_API_KEY=sk-xxx
CS_ROUTER_AI_REPLY=deepseek

# Translation (optional)
MINIMAX_API_KEY=xxx
CS_ROUTER_TRANSLATE=minimax
CS_ROUTER_DETECT_LANG=minimax

# Agents (optional, comma-separated Telegram user IDs)
CS_AGENTS=user1,user2
CS_ALLOWED_AGENTS=12345,67890

# Timeouts
CS_REPLY_TIMEOUT=180
CS_HEALTH_INTERVAL=30
EOF

# Run
.venv/bin/python examples/customer_service_poc.py

# Open in browser
# http://localhost:8081/chat
```

**POC architecture:**

```
Browser ──WebSocket──→ WebChatAdapter (:8081)
                              ↓
Mobile ──HTTP──→ WKIMCompatAdapter (:8080)     ChannelManager
                              ↓                     ↓
                         route by channel      on_message handler
                              ↓                     ↓
                     ┌── webchat/wkim ──→ forward_to_telegram()
                     │                         ↓
                     │              AI FAQ match? → reply directly
                     │                         ↓ (no match)
                     │              Create Telegram topic in support group
                     │              Agent sees customer message + user info
                     │
                     └── telegram ──→ forward_to_user()
                                         ↓
                              Agent reply → translate if needed → send to customer
                              /close → CSAT rating → close topic
```

**Agent commands (in Telegram support group):**

| Command | Description |
|---------|-------------|
| `/erp [ID]` | Query ERP user info |
| `/order [phone/ID]` | Query orders |
| `/tpl [name]` | Send quick reply template |
| `/ticket title` | Create a ticket |
| `/close` | Close session + send CSAT rating |
| `/history [N]` | View message history |
| `/lang` | Check user language + translation status |
| `/report [date]` | Daily report |
| `/hotwords [days]` | Hot keyword analysis |
| `/help` | Show all commands |

---

## 6. Configuration

See `config.example.yaml` for full reference.

```yaml
channels:
  telegram:
    token: "${TELEGRAM_BOT_TOKEN}"
  # webchat, whatsapp, wechat, line, discord, slack...

ai:
  backend: deepseek    # claude | deepseek | qwen | glm | minimax | openai
  api_key: "${AI_API_KEY}"
  model: deepseek-chat
  temperature: 0.3

escalation:
  max_ai_turns: 8      # Auto-escalate after N AI replies

agents:
  - id: agent-1
    name: Support Team
    channel: telegram
    chat_id: "${AGENT_CHAT_ID}"
    skills: [general]

dashboard:
  port: 8081

database:
  path: ./data/support.db
```

Environment variables are interpolated with `${VAR}` or `${VAR:-default}` syntax.

---

## 6. Quick Start

```bash
cd unified-support
cp config.example.yaml config.yaml
# Edit config.yaml with your tokens

pip install -e .
python -m support.app
# Dashboard: http://localhost:8081
```
