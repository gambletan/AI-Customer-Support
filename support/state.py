"""Shared runtime state — initialized by gateway.main()

All mutable globals live here so that handlers, forwarding, and translation
modules can import them without circular dependencies.
"""

from __future__ import annotations

import asyncio
import logging

from .config import Config
from .cs_store import CSStore
from .model_router import ModelRouter
from .infra.keyed_queue import KeyedAsyncQueue

logger = logging.getLogger("customer_service")

# --- Centralized config ---
cfg = Config()

# --- Model Router (task-based LLM routing) ---
router = ModelRouter.from_env()

# --- Persistent store (initialized async in gateway.main()) ---
store: CSStore | None = None  # type: ignore[assignment]

# --- In-memory caches ---
session_to_topic: dict[str, int] = {}
topic_to_session: dict[int, str] = {}
session_channel: dict[str, str] = {}

# Track pending replies for timeout alerts
pending_replies: dict[str, asyncio.Task] = {}  # session_id -> timeout task

# --- Waiting queue (when all agents are busy) ---
waiting_queue: list[str] = []  # list of session_ids awaiting assignment

# --- Keyed queue for per-customer message serialization ---
msg_queue = KeyedAsyncQueue()

# --- FAQ ---
FAQ: dict[str, str] = {
    "工作时间": "我们的客服工作时间是 周一至周五 9:00-18:00，周末 10:00-16:00。",
    "退货": "退货政策：自收货起7天内可无理由退货，请保持商品完好。需要我帮您办理退货吗？",
    "发货": "一般下单后1-3个工作日发货，您可以在订单详情查看物流信息。",
    "支付": "我们支持微信支付、支付宝、银行卡等多种支付方式。",
    "working hours": "Our service hours are Mon-Fri 9:00-18:00, Weekends 10:00-16:00.",
    "return": "Return policy: 7-day no-reason return from receipt. Want me to help process a return?",
    "shipping": "Orders ship within 1-3 business days. Check your order details for tracking.",
}

# --- Quick reply templates ---
TEMPLATES: dict[str, str] = {
    "欢迎": "您好！很高兴为您服务，请问有什么可以帮您？",
    "稍等": "好的，请您稍等，我帮您查一下。",
    "发货": "您的订单已发货，物流单号为 xxxxxx，请注意查收。",
    "退款": "退款申请已提交，预计1-3个工作日到账，请耐心等待。",
    "感谢": "感谢您的耐心等待，还有其他需要帮助的吗？",
    "结束": "感谢您的咨询，祝您生活愉快！如有需要随时联系我们。",
}

# --- Sensitive words ---
SENSITIVE_WORDS: list[str] = [
    # Add your sensitive words here
]
