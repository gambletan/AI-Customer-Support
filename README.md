# AI Customer Support

AI 原生全渠道智能客服系统。客户用任何 IM 直接对话，客服在 Telegram 统一接待。

## 运行模式

```
客户端 (浏览器 / 移动端 / IM)                 客服端 (Telegram)
┌─────────────────────────┐                 ┌────────────────────┐
│  WebChat (网页聊天)      │───┐             │  Telegram 超级群组   │
│  WuKongIM 兼容 (APP)     │───┼── Gateway ──│  每个客户 = 一个话题  │
│  Telegram 用户端 (可选)   │───┘   (aiohttp) │  客服直接在话题里回复  │
└─────────────────────────┘                 └────────────────────┘
        │                                           │
   ┌────┴────┐                                 ┌────┴────┐
   │ AI 自动  │  FAQ 匹配 / LLM 回复            │ Dashboard│
   │ 回复引擎  │  多模型路由                      │ REST API │
   └─────────┘                                 └─────────┘
```

### 核心工作流

1. **客户发消息** → Gateway 收到后在 Telegram 群组自动创建话题线程
2. **客服在话题中回复** → Gateway 把回复转发回客户的渠道
3. **AI 可选介入** → FAQ 关键词匹配 + LLM 自动回复，用户可随时「转人工」
4. **会话关闭** → 发送满意度评价 → 归档

### 使用场景

| 场景 | 说明 |
|------|------|
| **电商客服** | 嵌入 WebChat 到商城页面，客户咨询订单/退货/发货 |
| **SaaS 技术支持** | 多语言用户通过网页/IM 提交问题，自动翻译+AI 初筛 |
| **内部 IT Helpdesk** | 员工通过企业 IM 提问，AI 解答常见问题 |
| **跨境电商** | 自动检测客户语言，双向翻译，客服只需用中文回复 |

---

## 功能清单

### 渠道接入

| 渠道 | 类型 | 用户如何接入 |
|------|------|-------------|
| **Telegram** | Bot API | 扫码打开 `t.me/BOT` 私聊，直接和客服对话 |
| **WhatsApp** | Cloud API | 扫码打开 `wa.me/号码`，用自己的 WhatsApp 聊天 |
| **WebChat** | WebSocket | 嵌入式网页聊天，支持图片/视频/语音/文档 |
| **WuKongIM** | HTTP 兼容 | 对接现有悟空 IM 移动端 APP |

**扫码即聊：** 系统内置 QR 码生成端点 (`GET /qr`)，客户用手机扫一下就能在自己常用的 IM 里和客服对话，无需安装任何额外 APP。

### 智能功能

| 功能 | 开关 | 说明 |
|------|------|------|
| AI 自动回复 | `CS_FEATURE_AI_REPLY` | FAQ 关键词 + LLM 智能回复，不确定时提示转人工 |
| 语言检测 + 翻译 | `CS_FEATURE_TRANSLATION` | 自动检测用户语言，双向翻译（支持中/英/日/韩/法/德等 15 种） |
| 语音转文字 | `OPENAI_API_KEY` | Whisper API 自动将语音消息转为文字 |
| 敏感词过滤 | `CS_FEATURE_SENSITIVE_FILTER` | 检测敏感词并提醒客服 |
| 知识库 | `knowledge/*.md` | 放入 Markdown 文件即可作为 AI 回复的知识上下文 |

### 客服管理

| 功能 | 开关 | 说明 |
|------|------|------|
| 自动分配 | `CS_FEATURE_AGENT_ASSIGNMENT` | 最少负载分配，可配置每人最大会话数 |
| 排队机制 | `CS_FEATURE_QUEUE` | 客服满载时自动排队，空闲后自动分配 |
| 会话转接 | `/transfer <agent>` | 客服间一键转接 |
| 超时提醒 | `CS_FEATURE_TIMEOUT_ALERTS` | 客户等待超时自动提醒客服 |
| 权限管控 | `CS_FEATURE_ACCESS_CONTROL` | 白名单模式，自动踢出未授权成员 |
| 在线状态 | `CS_FEATURE_ONLINE_STATUS` | 客户上下线通知 |
| 消息历史 | `CS_FEATURE_HISTORY` | 重连后自动推送未读消息 |

### 运营工具

| 功能 | 命令 | 说明 |
|------|------|------|
| ERP 查询 | `/erp [ID]` | 查询客户信息（支持 Mock + REST API 对接） |
| 订单查询 | `/order [手机/ID]` | 查询订单详情 |
| 快捷回复 | `/tpl [模板名]` | 预设模板一键发送（自动翻译） |
| 工单系统 | `/ticket 标题` | 创建跟进工单 |
| 满意度评价 | `/close` | 关闭会话 + 5 星评分 |
| 日报统计 | `/report [日期]` | 会话数/消息量/平均响应/客服工作量 |
| 热词分析 | `/hotwords [天数]` | 用户高频关键词 |
| Dashboard API | `GET /api/*` | REST API 获取所有运营数据 |

### 基础设施

| 组件 | 说明 |
|------|------|
| 异步 SQLite (aiosqlite) | 会话/消息/工单/评价持久化，WAL 模式 |
| 按会话串行队列 | 同一客户消息 FIFO，不同客户并行 |
| 渠道健康监控 | 自动检测断线 + 指数退避重连 |
| 多模型路由 | 按任务路由到不同 LLM，自动 fallback |

---

## 快速开始

### 前置条件

- Python 3.10+
- Telegram Bot Token（通过 @BotFather 创建）
- 一个开启了 Topics/Forum 模式的 Telegram 超级群组
- 至少一个 LLM API Key（可选，用于 AI 回复/翻译）

### 安装

```bash
git clone https://github.com/gambletan/AI-Customer-Support.git
cd AI-Customer-Support
pip install -e ".[all-channels]"
```

### 配置（两种方式）

**方式 A：交互式向导（推荐）**

```bash
ai-cs setup
```

向导会引导你完成 5 步配置：Telegram Bot → 端口 → LLM 后端 → 客服设置 → 功能开关，自动生成 `.env` 文件。

**方式 B：手动配置**

创建 `.env` 文件（参考 `config.example.yaml`）：

```bash
# 必填
CS_TELEGRAM_TOKEN=123456:ABC-DEF
CS_SUPPORT_GROUP_ID=-1001234567890

# 可选：LLM
MINIMAX_API_KEY=sk-xxx          # 翻译
DEEPSEEK_API_KEY=sk-xxx         # AI 回复
OPENAI_API_KEY=sk-xxx           # Whisper 语音转文字

# 可选：客服
CS_AGENTS=alice,bob,charlie     # 客服名单
CS_MAX_SESSIONS_PER_AGENT=5     # 每人最大并发

# 可选：ERP 对接
CS_ERP_BACKEND=rest             # mock(默认) | rest
CS_ERP_BASE_URL=https://erp.example.com/api
CS_ERP_API_KEY=xxx
```

### 启动

```bash
ai-cs                           # 默认启动
ai-cs status                    # 检查配置
ai-cs setup                     # 重新配置
```

启动后访问：
- WebChat: `http://localhost:8081/chat`
- Dashboard API: `http://localhost:8081/api/sessions`
- WuKongIM: `http://localhost:8080`

---

## 对接指南

### 1. 扫码接入（推荐）

**最简单的方式：** 客户扫一个二维码，用自己的 Telegram 或 WhatsApp 直接开始对话。

```
用户手机                         你的服务器                      客服 Telegram 群组
  │                                │                              │
  ├─ 扫描二维码 ────────────────►  │                              │
  │  (t.me/BOT 或 wa.me/号码)     │                              │
  │                                │                              │
  ├─ 在自己的 IM 里发消息 ───────► │ Gateway 收到消息              │
  │                                ├─ 自动创建话题 ──────────────► │
  │                                │                              │ 客服在话题里回复
  │◄─ 收到客服回复 ───────────────  │◄──────────────────────────── │
```

**生成二维码：**

启动服务后，访问 QR 端点：

```bash
# Telegram 二维码
http://localhost:8081/qr

# WhatsApp 二维码
http://localhost:8081/qr?ch=whatsapp

# 带引荐参数（可追踪来源）
http://localhost:8081/qr?start=campaign_spring2026

# PNG 格式（默认 SVG）
http://localhost:8081/qr?format=png&scale=10
```

把生成的二维码放在你的网站、物料、包裹卡片上，客户扫码即可。

**Telegram 对接流程：**
1. 客户扫码 → 打开 `t.me/你的Bot` → 点击 Start
2. Bot 自动发欢迎语，在客服群组创建话题
3. 客户在 Telegram 私聊里发消息 ↔ 客服在群组话题里回复

**WhatsApp 对接流程：**
1. 客户扫码 → 打开 `wa.me/你的号码`
2. 客户发消息 → Gateway 收到 Webhook → 创建话题
3. 客户在 WhatsApp 里发消息 ↔ 客服在群组话题里回复

### 2. WebChat 网页嵌入

在你的网站页面中嵌入 iframe：

```html
<iframe src="http://your-server:8081/chat" width="420" height="680"
        style="border:none; border-radius:16px; box-shadow:0 4px 24px rgba(0,0,0,0.12);">
</iframe>
```

**带用户身份（登录用户）：**

```html
<!-- 方式 1: URL 参数 -->
<iframe src="http://your-server:8081/chat?user_id=C10086&name=张三&phone=13800138000">
</iframe>

<!-- 方式 2: JS API -->
<script>
  const chatFrame = document.getElementById('chat-frame');
  chatFrame.contentWindow.postMessage({
    type: 'chat_user',
    user_id: 'C10086',
    name: '张三',
    phone: '13800138000'
  }, '*');
</script>
```

传入 `user_id` 后的效果：
- Telegram 话题名显示客户姓名而非匿名访客
- 客服可用 `/erp C10086` 查询该客户的 ERP 信息
- 会话跟随用户（换设备/重连自动恢复）

**生成接入二维码：**

将 WebChat URL 生成二维码，客户手机扫码即可打开网页聊天：

```bash
# 使用任意二维码工具
qrencode -o chat-qr.png "https://your-domain.com/chat"
# 或用 Python
python3 -c "import qrcode; qrcode.make('https://your-domain.com/chat').save('chat-qr.png')"
```

### 3. WuKongIM 移动端对接

如果你已有使用悟空 IM SDK 的移动 APP，Gateway 的 WuKongIM 兼容端口（默认 8080）可直接对接：

```
APP 配置 → 服务器地址: http://your-server:8080
```

消息格式兼容悟空 IM 协议，无需修改 APP 代码。

### 4. ERP / 业务系统对接

设置 `CS_ERP_BACKEND=rest` 后，客服使用 `/erp` 和 `/order` 命令时会调用你的 REST API：

```
GET /customer?q={user_id_or_phone}
→ { "id": "C10086", "name": "张三", "phone": "138xxx", "level": "金牌", ... }

GET /orders?q={user_id_or_phone}&limit=5
→ { "orders": [{ "id": "#202601", "amount": 299, "status": "已发货", ... }] }
```

只需实现这两个接口，客服就能在 Telegram 中一键查询客户和订单。

### 5. Dashboard API 对接

所有运营数据通过 REST API 暴露，可接入自有 BI 系统：

```
GET /api/sessions              # 活跃会话列表
GET /api/sessions/{id}         # 会话详情 + 消息记录
GET /api/report?date=2026-03-10  # 日报统计
GET /api/hotwords?days=7&top=20  # 热词分析
GET /api/agents/load           # 客服负载
GET /api/queue                 # 排队队列
```

### 6. 自定义 AI 知识库

在 `knowledge/` 目录放入 Markdown 文件即可：

```bash
knowledge/
  faq.md          # 常见问题
  products.md     # 产品说明
  policies.md     # 退换货政策
  shipping.md     # 物流说明
```

AI 回复时会自动搜索知识库内容作为上下文。

---

## 进一步简化对接

### 已有的简化措施

1. **零前端开发** — WebChat 是自带的完整 UI，iframe 嵌入一行代码
2. **交互式配置** — `ai-cs setup` 向导式 5 步配置
3. **Mock ERP** — 无需真实 ERP 也能演示完整流程
4. **Feature Toggles** — 13 个功能开关，按需启用
5. **自动 Fallback** — LLM 后端自动降级，不会因单个服务不可用导致功能全失

### 未来可进一步简化的方向

| 方向 | 说明 | 预计工作量 |
|------|------|-----------|
| **一键 Docker 部署** | `docker compose up` 即可运行，包含 Nginx 反向代理 + HTTPS | 2h |
| **WebChat JS SDK** | `<script src="chat.js">` 浮窗挂件，无需 iframe | 3h |
| **微信公众号适配器** | 扫码关注即对话（unified-channel 已有 wechat adapter） | 4h |
| **企业微信适配器** | 对接企微客服 API（unified-channel 已有 feishu/dingtalk） | 4h |
| **更多 IM 渠道** | LINE / Discord / Slack 等（unified-channel 已有 25 个 adapter） | 2h/渠道 |
| **管理后台前端** | Dashboard 可视化页面（替代 curl API） | 6h |
| **Webhook 通知** | 新会话/超时/关闭时推送到企业系统 | 2h |
| **OAuth 单点登录** | 客户通过 SSO 自动绑定身份，免手动传 user_id | 4h |

---

## 环境变量参考

### 核心配置

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `CS_TELEGRAM_TOKEN` | 是 | — | Telegram Bot Token |
| `CS_SUPPORT_GROUP_ID` | 是 | — | 超级群组 ID（以 -100 开头） |
| `WEBCHAT_PORT` | 否 | 8081 | WebChat + Dashboard 端口 |
| `WKIM_PORT` | 否 | 8080 | WuKongIM 兼容端口 |
| `CS_DB_PATH` | 否 | cs_data.db | SQLite 数据库路径 |

### LLM 后端

| 变量 | 说明 |
|------|------|
| `MINIMAX_API_KEY` | MiniMax（推荐翻译） |
| `DEEPSEEK_API_KEY` | DeepSeek（推荐 AI 回复） |
| `OPENAI_API_KEY` | OpenAI（Whisper 语音 + 备选） |
| `QWEN_API_KEY` | 通义千问 |
| `GLM_API_KEY` | 智谱 GLM |
| `CLAUDE_API_KEY` | Anthropic Claude |
| `CS_ROUTER_TRANSLATE` | 翻译任务路由（默认 minimax） |
| `CS_ROUTER_AI_REPLY` | AI 回复路由（默认 deepseek） |
| `CS_ROUTER_DETECT_LANG` | 语言检测路由（默认 minimax） |
| `CS_ROUTER_SUMMARIZE` | 摘要路由（默认 deepseek） |

### 客服管理

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CS_AGENTS` | (空) | 客服名单，逗号分隔 |
| `CS_MAX_SESSIONS_PER_AGENT` | 5 | 每客服最大并发会话 |
| `CS_ALLOWED_AGENTS` | (空) | 白名单 Telegram User ID |
| `CS_REPLY_TIMEOUT` | 180 | 超时提醒秒数 |
| `CS_HEALTH_INTERVAL` | 30 | 健康检查间隔秒数 |

### WhatsApp（可选）

| 变量 | 说明 |
|------|------|
| `CS_WA_ACCESS_TOKEN` | Meta Business 永久 Access Token |
| `CS_WA_PHONE_NUMBER_ID` | WhatsApp Business Phone Number ID |
| `CS_WA_VERIFY_TOKEN` | Webhook 验证 Token（自定义） |
| `CS_WA_APP_SECRET` | App Secret（HMAC 签名验证，可选） |
| `CS_WA_PORT` | Webhook 端口（默认 8443） |
| `CS_WA_PHONE_NUMBER` | 显示号码，用于 `wa.me` 链接 |

### ERP 对接

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CS_ERP_BACKEND` | mock | `mock` 或 `rest` |
| `CS_ERP_BASE_URL` | — | REST API 地址 |
| `CS_ERP_API_KEY` | — | REST API 认证 Key |
| `CS_ERP_TIMEOUT` | 5 | 请求超时秒数 |

### 功能开关

所有功能开关均以 `CS_FEATURE_` 为前缀，值为 `true`/`false`：

| 开关 | 默认 | 说明 |
|------|------|------|
| `TRANSLATION` | true | 自动翻译 |
| `AI_REPLY` | false | AI 自动回复 |
| `QUEUE` | true | 排队机制 |
| `AGENT_ASSIGNMENT` | true | 自动分配 |
| `SENSITIVE_FILTER` | false | 敏感词 |
| `RATINGS` | true | 满意度评价 |
| `TICKETS` | true | 工单系统 |
| `TIMEOUT_ALERTS` | true | 超时提醒 |
| `ACCESS_CONTROL` | false | 权限管控 |
| `REPORTS` | true | 报表分析 |
| `TEMPLATES` | true | 快捷模板 |
| `ONLINE_STATUS` | true | 在线状态 |
| `HISTORY` | true | 消息历史 |

---

## 项目结构

```
support/
  cli.py                 # CLI 入口 (ai-cs)
  config.py              # 配置 + 功能开关
  setup.py               # 交互式配置向导
  gateway.py             # 网关启动 + 渠道连接
  state.py               # 共享运行时状态
  forwarding.py          # 消息转发 (用户 <-> Telegram)
  handlers.py            # 客服命令处理 (/erp, /close, ...)
  translation.py         # 语言检测 + 翻译
  cs_store.py            # 异步 SQLite 持久化
  model_router.py        # 多模型 LLM 路由
  erp.py                 # ERP 适配器 (Mock + REST)
  telegram_gateway.py    # 向后兼容 re-export
  dashboard/
    api.py               # Dashboard REST API
    static/
      chat.html          # WebChat 前端
  infra/
    keyed_queue.py       # 按 key 串行的异步队列
    health.py            # 渠道健康监控 + 自动重连
knowledge/               # AI 知识库 (Markdown)
tests/                   # 测试套件 (54 tests)
```

---

## 客服端命令

在 Telegram 话题中可用的命令：

| 命令 | 说明 |
|------|------|
| `/erp [ID]` | 查询客户 ERP 信息 |
| `/order [手机/ID]` | 查询订单 |
| `/tpl [模板名]` | 发送快捷回复模板 |
| `/ticket 标题` | 创建工单 |
| `/transfer <客服名>` | 转接会话 |
| `/close` | 关闭会话 + 评价 |
| `/history [N]` | 查看最近 N 条消息 |
| `/report [日期]` | 日报统计 |
| `/hotwords [天数]` | 热词分析 |
| `/queue` | 查看排队用户 |
| `/lang` | 查看用户语言 + 翻译状态 |
| `/help` | 显示所有命令 |

---

## License

MIT
