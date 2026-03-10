# API 对接文档

AI Customer Support 系统提供以下 API 接口，用于前端集成、数据查询和业务系统对接。

基础地址: `http://localhost:8081`（WebChat 端口，Dashboard API 共用同一端口）

---

## 目录

- [1. WebSocket 聊天协议](#1-websocket-聊天协议)
- [2. Dashboard REST API](#2-dashboard-rest-api)
- [3. 二维码与渠道选择页](#3-二维码与渠道选择页)
- [4. IM 渠道接入配置](#4-im-渠道接入配置)
- [5. ERP / 业务系统对接](#5-erp--业务系统对接)
- [6. WebChat 嵌入集成](#6-webchat-嵌入集成)
- [7. 完整环境变量参考](#7-完整环境变量参考)

---

## 1. WebSocket 聊天协议

WebChat 前端通过 WebSocket 与 Gateway 通信。

### 连接

```
ws://{host}:{port}/ws[?params]
```

**URL 参数（可选）：**

| 参数 | 说明 |
|------|------|
| `user_id` | 已登录用户 ID（传入后话题显示用户名，支持 ERP 查询） |
| `name` | 用户显示名称 |
| `phone` | 用户手机号 |
| `session_id` | 恢复匿名会话（从 `localStorage` 读取） |

**示例：**

```javascript
// 匿名用户
const ws = new WebSocket("ws://localhost:8081/ws");

// 已登录用户
const ws = new WebSocket("ws://localhost:8081/ws?user_id=C10086&name=张三&phone=13800138000");
```

### 客户端 → 服务端

#### 发送文本

```json
{ "type": "text", "text": "你好，我想查询订单" }
```

#### 发送媒体（图片/视频/语音/文档）

```json
{
  "type": "media",
  "media_type": "image",
  "data": "data:image/jpeg;base64,/9j/4AAQ...",
  "text": "",
  "filename": "photo.jpg"
}
```

`media_type` 枚举:

| 值 | 说明 | 格式 |
|----|------|------|
| `image` | 图片 | jpg, png, gif, webp |
| `video` | 视频 | mp4, webm, mov |
| `voice` | 语音 | ogg, mp3, wav, m4a |
| `document` | 文档 | pdf, doc, docx, xls, xlsx, ppt, pptx, txt, zip |

#### 身份认证（连接后动态绑定）

```json
{
  "type": "auth",
  "user_id": "C10086",
  "name": "张三",
  "phone": "13800138000"
}
```

#### 回调（评分）

```json
{ "type": "callback", "callback_data": "rate:session_abc:5" }
```

### 服务端 → 客户端

#### 系统消息

```json
{
  "type": "system",
  "text": "connected",
  "session_id": "abc123",
  "user_type": "authenticated"
}
```

`text` 枚举: `connected`（初次连接）, `authenticated`（身份验证成功）

#### 文本消息（客服回复）

```json
{ "type": "text", "text": "您好，请提供订单号" }
```

#### 带按钮消息（评分）

```json
{
  "type": "text",
  "text": "请为本次服务评分：",
  "buttons": [[
    {"label": "⭐", "callback_data": "rate:sess_id:1"},
    {"label": "⭐⭐", "callback_data": "rate:sess_id:2"},
    {"label": "⭐⭐⭐", "callback_data": "rate:sess_id:3"},
    {"label": "⭐⭐⭐⭐", "callback_data": "rate:sess_id:4"},
    {"label": "⭐⭐⭐⭐⭐", "callback_data": "rate:sess_id:5"}
  ]]
}
```

#### 媒体消息

```json
{
  "type": "media",
  "text": "这是截图",
  "url": "https://api.telegram.org/file/bot.../photo.jpg",
  "media_type": "image",
  "filename": "screenshot.png"
}
```

#### 历史消息（重连后推送）

```json
{
  "type": "history",
  "messages": [
    {
      "sender": "user",
      "text": "你好",
      "media_url": null,
      "media_type": null,
      "timestamp": "2026-03-10 14:30:00"
    },
    {
      "sender": "agent",
      "text": "您好，有什么可以帮您？",
      "media_url": null,
      "media_type": null,
      "timestamp": "2026-03-10 14:30:15"
    }
  ]
}
```

#### 未读通知

```json
{ "type": "unseen_notice", "count": 3 }
```

#### 输入状态

```json
{ "type": "typing" }
```

### 连接生命周期

```
客户端                           服务端
  │                                │
  ├─ WebSocket connect ──────────► │  分配 session_id
  │◄──── {type:"system"} ──────── │
  │                                │
  ├─ {type:"text"} ──────────────► │  转发到 Telegram 话题
  │                                │
  │◄── {type:"text"} ───────────── │  客服回复
  │                                │
  │  (断线重连)                     │
  ├─ ws://host/ws?session_id=xxx ► │
  │◄── {type:"unseen_notice"} ──── │
  │◄── {type:"history"} ────────── │
```

---

## 2. Dashboard REST API

所有接口返回 JSON，挂载在 WebChat 同一端口。

### GET /api/sessions

获取所有活跃会话列表。

**响应：**

```json
{
  "sessions": [
    {
      "session_id": "abc123",
      "channel": "webchat",
      "user_type": "authenticated",
      "user_id": "C10086",
      "user_name": "张三",
      "user_phone": "13800138000",
      "assigned_agent": "alice",
      "topic_id": 42,
      "created_at": "2026-03-10 14:00:00",
      "closed_at": null,
      "first_reply_at": "2026-03-10 14:01:30",
      "has_topic": true
    }
  ],
  "count": 1
}
```

### GET /api/sessions/{session_id}

获取单个会话详情 + 消息记录 + 评分 + 工单。

**参数：**

| 参数 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `session_id` | path | — | 会话 ID |
| `limit` | query | 50 | 返回消息条数 |

**响应 200：**

```json
{
  "session": {
    "session_id": "abc123",
    "channel": "webchat",
    "user_type": "authenticated",
    "user_id": "C10086",
    "user_name": "张三",
    "assigned_agent": "alice",
    "created_at": "2026-03-10 14:00:00",
    "closed_at": null
  },
  "messages": [
    {
      "id": 1,
      "sender": "user",
      "content": "你好，我想查询订单",
      "media_url": null,
      "media_type": null,
      "timestamp": "2026-03-10 14:00:05"
    },
    {
      "id": 2,
      "sender": "agent",
      "content": "您好，请提供订单号",
      "media_url": null,
      "media_type": null,
      "timestamp": "2026-03-10 14:01:30"
    }
  ],
  "rating": { "score": 5, "created_at": "2026-03-10 14:30:00" },
  "tickets": [
    { "id": 1, "title": "退货问题", "status": "open", "created_by": "alice", "created_at": "2026-03-10 14:10:00" }
  ]
}
```

**响应 404：**

```json
{"error": "session not found"}
```

### GET /api/report

获取日报统计。

**参数：**

| 参数 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `date` | query | 今天 | 格式 `YYYY-MM-DD` |

**响应：**

```json
{
  "date": "2026-03-10",
  "total_sessions": 42,
  "closed_sessions": 38,
  "total_messages": 256,
  "avg_rating": 4.6,
  "avg_first_reply_seconds": 45,
  "agents": [
    {"assigned_agent": "alice", "sessions": 15, "replies": 80},
    {"assigned_agent": "bob", "sessions": 12, "replies": 65}
  ]
}
```

### GET /api/hotwords

获取热门关键词。

**参数：**

| 参数 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `days` | query | 7 | 统计天数 |
| `top` | query | 20 | 返回 Top N |

**响应：**

```json
{
  "days": 7,
  "keywords": [
    {"word": "退货", "count": 28},
    {"word": "发货", "count": 22},
    {"word": "订单", "count": 18}
  ]
}
```

### GET /api/agents/load

获取客服负载。

**响应：**

```json
{
  "agents": [
    {"name": "alice", "active_sessions": 3},
    {"name": "bob", "active_sessions": 5}
  ],
  "configured_agents": ["alice", "bob", "charlie"],
  "max_per_agent": 5
}
```

### GET /api/queue

获取等待队列。

**响应：**

```json
{
  "queue": [
    {
      "session_id": "xyz789",
      "user_name": "李四",
      "user_id": "C10087",
      "created_at": "2026-03-10 15:00:00"
    }
  ],
  "count": 1
}
```

---

## 3. 二维码与渠道选择页

系统提供**统一二维码**入口。用户扫一个码，选择自己常用的 IM 渠道开始对话。

### GET /qr

生成二维码图片，指向 `/connect` 渠道选择页。

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `format` | svg | `svg` 或 `png` |
| `scale` | 8 | 缩放倍数 |

```bash
# SVG（适合网页）
curl http://localhost:8081/qr -o connect.svg

# PNG（适合打印）
curl "http://localhost:8081/qr?format=png&scale=10" -o connect.png
```

### GET /connect

渠道选择落地页。自动列出所有已启用渠道的按钮：

- **Telegram** → `https://t.me/{bot_username}`
- **Web Chat** → `/chat`
- **WhatsApp** → `https://wa.me/{phone}`（需配 `CS_WA_PHONE_NUMBER`）
- **LINE** → `https://line.me/R/oaMessage/{bot_id}`（需配 `CS_LINE_BOT_ID`）
- 其他已配置渠道的深度链接

**流程：**

```
二维码 ──► /connect 落地页 ──► 用户选择渠道
                                ├── Telegram  → t.me/BOT
                                ├── WhatsApp  → wa.me/PHONE
                                ├── LINE      → line.me/...
                                ├── Web Chat  → /chat
                                └── ...
```

**环境变量：**

| 变量 | 说明 |
|------|------|
| `CS_BASE_URL` | 公网基地址（反向代理时必设），如 `https://cs.example.com` |

---

## 4. IM 渠道接入配置

支持 12 个 IM 渠道。设置对应环境变量即可自动启用，Gateway 启动时自动检测。

### 渠道列表

| 渠道 | 环境变量前缀 | 必填 Key | 可选 Key | 默认端口 |
|------|-------------|----------|----------|---------|
| WhatsApp | `CS_WA_` | `ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN` | `APP_SECRET`, `PORT`, `PHONE_NUMBER` | 8443 |
| LINE | `CS_LINE_` | `CHANNEL_SECRET`, `CHANNEL_ACCESS_TOKEN` | `PORT` | 8044 |
| Discord | `CS_DISCORD_` | `TOKEN` | — | — |
| Slack | `CS_SLACK_` | `BOT_TOKEN`, `APP_TOKEN` | — | — |
| WeChat (Enterprise) | `CS_WECHAT_` | `CORP_ID`, `CORP_SECRET`, `AGENT_ID` | `TOKEN`, `ENCODING_AES_KEY`, `PORT` | 9001 |
| Feishu (Lark) | `CS_FEISHU_` | `APP_ID`, `APP_SECRET` | `VERIFICATION_TOKEN`, `ENCRYPT_KEY`, `PORT` | 9000 |
| DingTalk | `CS_DINGTALK_` | `APP_KEY`, `APP_SECRET` | `WEBHOOK_URL`, `SECRET`, `PORT` | 9002 |
| MS Teams | `CS_TEAMS_` | `APP_ID`, `APP_PASSWORD` | `PORT` | 3978 |
| QQ | `CS_QQ_` | `APP_ID`, `TOKEN` | `SECRET`, `SANDBOX` | — |
| Matrix | `CS_MATRIX_` | `HOMESERVER`, `USER_ID` | `PASSWORD`, `ACCESS_TOKEN` | — |
| Zalo | `CS_ZALO_` | `ACCESS_TOKEN` | `APP_SECRET`, `PORT` | 8060 |
| iMessage | `CS_IMESSAGE_` | `ENABLED` | `ALLOWED_NUMBERS`, `POLL_INTERVAL` | — |

### 配置示例

```bash
# .env

# WhatsApp — Meta Business Cloud API
CS_WA_ACCESS_TOKEN=EAAxxxxxxxxx
CS_WA_PHONE_NUMBER_ID=1234567890
CS_WA_VERIFY_TOKEN=my_verify_token
CS_WA_PHONE_NUMBER=8613800138000

# 飞书
CS_FEISHU_APP_ID=cli_xxxxxxxx
CS_FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx

# 企业微信
CS_WECHAT_CORP_ID=wwxxxxxxxx
CS_WECHAT_CORP_SECRET=xxxxxxxxxxxxxxxx
CS_WECHAT_AGENT_ID=1000002

# Discord
CS_DISCORD_TOKEN=MTxxxxxxxx.xxxxxxxx.xxxxxxxx
```

### 深度链接（/connect 页面用）

| 渠道 | 环境变量 | 链接格式 |
|------|---------|---------|
| WhatsApp | `CS_WA_PHONE_NUMBER` | `https://wa.me/{value}` |
| LINE | `CS_LINE_BOT_ID` | `https://line.me/R/oaMessage/{value}` |

### 交互式配置

```bash
ai-cs setup
# Step 4/6 引导配置各渠道 API 凭据
```

### 架构

```
.env 环境变量 ──► get_enabled_channels() ──► create_adapter() ──► ChannelManager
                   自动检测                    约定式工厂             统一路由
```

添加新渠道只需在 `support/channels.py` 的 `CHANNELS` 列表加一个 `ChannelDef`。

---

## 5. ERP / 业务系统对接

客服使用 `/erp` 和 `/order` 命令时，系统调用你的 REST API。

### 配置

```bash
CS_ERP_BACKEND=rest                        # mock(默认) | rest
CS_ERP_BASE_URL=https://erp.example.com/api
CS_ERP_API_KEY=your_api_key
CS_ERP_TIMEOUT=5
```

### 你需要实现的接口

#### GET /customer

```
GET {CS_ERP_BASE_URL}/customer?q={user_id_or_phone}
Authorization: Bearer {CS_ERP_API_KEY}
```

**响应：**

```json
{
  "id": "C10086",
  "name": "张三",
  "phone": "13800138000",
  "level": "金牌",
  "balance": 1500.00,
  "created_at": "2025-01-15",
  "tags": ["VIP", "电商"]
}
```

#### GET /orders

```
GET {CS_ERP_BASE_URL}/orders?q={user_id_or_phone}&limit=5
Authorization: Bearer {CS_ERP_API_KEY}
```

**响应：**

```json
{
  "orders": [
    {
      "id": "#202603100001",
      "amount": 299.00,
      "status": "已发货",
      "items": "iPhone 手机壳 x1",
      "created_at": "2026-03-08",
      "tracking": "SF1234567890"
    }
  ]
}
```

### Mock 模式

`CS_ERP_BACKEND=mock`（默认）使用内置模拟数据，无需 ERP 即可演示完整流程。

---

## 6. WebChat 嵌入集成

### iframe 嵌入

```html
<iframe
  src="https://cs.example.com/chat"
  width="420" height="680"
  style="border:none; border-radius:16px; box-shadow:0 4px 24px rgba(0,0,0,0.12);">
</iframe>
```

### 传递用户身份

三种方式（优先级递增）：

#### 方式 1：URL 参数

```html
<iframe src="https://cs.example.com/chat?user_id=C10086&name=张三&phone=13800138000"></iframe>
```

#### 方式 2：JS 全局变量

```html
<script>
window.CHAT_USER = { user_id: "C10086", name: "张三", phone: "13800138000" };
</script>
<iframe src="https://cs.example.com/chat"></iframe>
```

#### 方式 3：postMessage（动态绑定）

```javascript
const chatFrame = document.getElementById('chat-iframe');
chatFrame.contentWindow.postMessage({
  type: 'chat_user',
  user_id: 'C10086',
  name: '张三',
  phone: '13800138000',
  extra: { vip: true }
}, '*');
```

### 身份传入效果

| 能力 | 匿名 | 已登录 |
|------|------|--------|
| Telegram 话题标题 | `💬 访客_abc123` | `👤 张三` |
| ERP 查询 | 不可用 | `/erp C10086` |
| 跨设备恢复 | 同浏览器 (localStorage) | 任何设备 |

### 代码示例

#### 最小化 WebSocket 客户端

```javascript
const ws = new WebSocket('ws://localhost:8081/ws?user_id=C10086&name=张三');

ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  switch (data.type) {
    case 'system':
      console.log(`Connected: session=${data.session_id}`);
      break;
    case 'text':
      console.log(`Agent: ${data.text}`);
      break;
    case 'media':
      console.log(`Agent media: ${data.media_type} ${data.url}`);
      break;
    case 'history':
      data.messages.forEach(m => console.log(`[${m.sender}] ${m.text}`));
      break;
  }
};

// 发送文本
ws.send(JSON.stringify({ type: 'text', text: '你好' }));

// 发送图片
ws.send(JSON.stringify({
  type: 'media', media_type: 'image',
  data: 'data:image/png;base64,...', text: ''
}));
```

#### Python 调用 Dashboard API

```python
import httpx

BASE = "http://localhost:8081"

async def main():
    async with httpx.AsyncClient() as c:
        # 活跃会话
        r = await c.get(f"{BASE}/api/sessions")
        sessions = r.json()
        print(f"Active: {sessions['count']}")

        # 会话详情 + 消息
        if sessions['sessions']:
            sid = sessions['sessions'][0]['session_id']
            r = await c.get(f"{BASE}/api/sessions/{sid}")
            detail = r.json()
            for msg in detail['messages']:
                print(f"  [{msg['sender']}] {msg['content']}")

        # 日报
        r = await c.get(f"{BASE}/api/report")
        report = r.json()
        print(f"Today: {report['total_sessions']} sessions, avg rating {report['avg_rating']}")

        # 客服负载
        r = await c.get(f"{BASE}/api/agents/load")
        for agent in r.json()['agents']:
            print(f"  {agent['name']}: {agent['active_sessions']} sessions")

import asyncio
asyncio.run(main())
```

---

## 7. 完整环境变量参考

### 核心（必填）

| 变量 | 说明 |
|------|------|
| `CS_TELEGRAM_TOKEN` | Telegram Bot Token |
| `CS_SUPPORT_GROUP_ID` | 超级群组 ID（以 `-100` 开头） |

### 端口

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEBCHAT_PORT` | 8081 | WebChat + Dashboard + QR |
| `WKIM_PORT` | 8080 | WuKongIM 兼容端口 |
| `CS_BASE_URL` | — | 公网基地址（反向代理时设置） |

### LLM

| 变量 | 说明 |
|------|------|
| `MINIMAX_API_KEY` | MiniMax（推荐翻译） |
| `DEEPSEEK_API_KEY` | DeepSeek（推荐 AI 回复） |
| `OPENAI_API_KEY` | OpenAI（Whisper 语音 + 备选） |
| `QWEN_API_KEY` | 通义千问 |
| `GLM_API_KEY` | 智谱 GLM |
| `CLAUDE_API_KEY` | Anthropic Claude |
| `CS_ROUTER_TRANSLATE` | 翻译路由（默认 minimax） |
| `CS_ROUTER_AI_REPLY` | AI 回复路由（默认 deepseek） |
| `CS_ROUTER_DETECT_LANG` | 语言检测路由（默认 minimax） |
| `CS_ROUTER_SUMMARIZE` | 摘要路由（默认 deepseek） |

### 客服

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CS_AGENTS` | — | 客服名单（逗号分隔） |
| `CS_MAX_SESSIONS_PER_AGENT` | 5 | 每客服最大并发 |
| `CS_ALLOWED_AGENTS` | — | 白名单 Telegram User ID |
| `CS_REPLY_TIMEOUT` | 180 | 超时提醒秒数 |
| `CS_HEALTH_INTERVAL` | 30 | 健康检查间隔秒数 |

### ERP

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CS_ERP_BACKEND` | mock | `mock` 或 `rest` |
| `CS_ERP_BASE_URL` | — | REST API 地址 |
| `CS_ERP_API_KEY` | — | API 认证 Key |
| `CS_ERP_TIMEOUT` | 5 | 请求超时秒数 |

### 功能开关

前缀 `CS_FEATURE_`，值 `true`/`false`：

| 开关 | 默认 | 说明 |
|------|------|------|
| `TRANSLATION` | true | 自动翻译 |
| `AI_REPLY` | false | AI 自动回复 |
| `QUEUE` | true | 排队机制 |
| `AGENT_ASSIGNMENT` | true | 自动分配 |
| `SENSITIVE_FILTER` | false | 敏感词检测 |
| `RATINGS` | true | 满意度评价 |
| `TICKETS` | true | 工单系统 |
| `TIMEOUT_ALERTS` | true | 超时提醒 |
| `ACCESS_CONTROL` | false | 权限管控 |
| `REPORTS` | true | 报表分析 |
| `TEMPLATES` | true | 快捷模板 |
| `ONLINE_STATUS` | true | 在线状态 |
| `HISTORY` | true | 消息历史 |

---

## 附录：客服端 Telegram 命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/erp [ID]` | 查询客户 ERP 信息 | `/erp C10086` |
| `/order [手机/ID]` | 查询订单 | `/order 13800138000` |
| `/tpl [模板名]` | 发送快捷回复（自动翻译） | `/tpl greeting` |
| `/ticket 标题` | 创建跟进工单 | `/ticket 退货问题` |
| `/transfer <客服>` | 转接到其他客服 | `/transfer bob` |
| `/close` | 关闭会话 + 发送评分 | `/close` |
| `/history [N]` | 查看最近 N 条消息 | `/history 30` |
| `/report [日期]` | 日报统计 | `/report 2026-03-10` |
| `/hotwords [天数]` | 热词分析 | `/hotwords 14` |
| `/queue` | 查看排队队列 | `/queue` |
| `/lang` | 查看用户语言 + 翻译状态 | `/lang` |
| `/help` | 显示所有命令 | `/help` |
