"""ERP adapter — pluggable backend for customer and order queries.

Backends:
    mock    — built-in fake data for testing (default)
    rest    — generic REST API (configurable URL + key)

Configuration:
    CS_ERP_BACKEND=mock|rest
    CS_ERP_BASE_URL=https://erp.example.com/api   (rest only)
    CS_ERP_API_KEY=xxx                              (rest only)
    CS_ERP_TIMEOUT=5                                (seconds)
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class Customer:
    id: str
    name: str | None = None
    phone: str | None = None
    registered_at: str | None = None
    level: str | None = None
    total_spent: float = 0
    order_count: int = 0
    tags: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def format(self) -> str:
        lines = [f"📋 客户信息"]
        lines.append(f"• ID: `{self.id}`")
        if self.name:
            lines.append(f"• 姓名: {self.name}")
        if self.phone:
            lines.append(f"• 手机: {self.phone}")
        if self.registered_at:
            lines.append(f"• 注册: {self.registered_at}")
        if self.level:
            lines.append(f"• 等级: {self.level}")
        if self.total_spent:
            lines.append(f"• 累计消费: ¥{self.total_spent:,.0f}")
        if self.order_count:
            lines.append(f"• 订单数: {self.order_count}")
        if self.tags:
            lines.append(f"• 标签: {', '.join(self.tags)}")
        return "\n".join(lines)


@dataclass
class Order:
    id: str
    amount: float
    status: str
    created_at: str
    items: str = ""
    tracking: str = ""

    def format_line(self) -> str:
        s = f"`{self.id}` — ¥{self.amount:.0f} {self.status} ({self.created_at})"
        if self.tracking:
            s += f" 📦{self.tracking}"
        return s


class ERPAdapter:
    """Base ERP adapter interface."""

    async def get_customer(self, query: str) -> Customer | None:
        """Query customer by ID, phone, or name."""
        raise NotImplementedError

    async def get_orders(self, query: str, limit: int = 5) -> list[Order]:
        """Query orders by customer ID, phone, or order number."""
        raise NotImplementedError


class MockERPAdapter(ERPAdapter):
    """Mock adapter with realistic fake data for testing."""

    _NAMES = ["张三", "李四", "王五", "赵六", "陈七", "刘八", "孙九", "周十",
              "John Smith", "Maria Garcia", "Pierre Dupont", "Yuki Tanaka"]
    _LEVELS = ["普通", "银牌", "金牌", "钻石"]
    _STATUSES = ["待发货", "已发货", "运输中", "已签收", "退款中", "退款完成"]
    _ITEMS = ["蓝牙耳机", "手机壳", "充电宝", "数据线", "键盘", "鼠标",
              "T恤", "运动鞋", "背包", "保温杯", "护肤套装", "零食礼盒"]
    _TAGS = ["高价值", "新客", "活跃", "流失风险", "VIP", "批发"]

    def __init__(self) -> None:
        # Cache so same query returns consistent data within session
        self._customer_cache: dict[str, Customer] = {}
        self._order_cache: dict[str, list[Order]] = {}

    async def get_customer(self, query: str) -> Customer | None:
        if not query:
            return None

        if query in self._customer_cache:
            return self._customer_cache[query]

        # Generate deterministic-ish data from query hash
        h = hash(query)
        rng = random.Random(h)

        days_ago = rng.randint(30, 800)
        reg_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        order_count = rng.randint(1, 50)
        avg_order = rng.uniform(50, 500)

        customer = Customer(
            id=query if not query.startswith("1") else f"C{query[-6:]}",
            name=rng.choice(self._NAMES),
            phone=f"1{rng.randint(30, 99)}{''.join(str(rng.randint(0,9)) for _ in range(8))}",
            registered_at=reg_date,
            level=rng.choice(self._LEVELS),
            total_spent=round(order_count * avg_order, 2),
            order_count=order_count,
            tags=rng.sample(self._TAGS, k=rng.randint(0, 3)),
        )
        self._customer_cache[query] = customer
        return customer

    async def get_orders(self, query: str, limit: int = 5) -> list[Order]:
        if not query:
            return []

        if query in self._order_cache:
            return self._order_cache[query][:limit]

        h = hash(query)
        rng = random.Random(h)
        count = rng.randint(1, 8)

        orders = []
        for i in range(count):
            days_ago = rng.randint(1, 180)
            date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            status = rng.choice(self._STATUSES)
            tracking = ""
            if status in ("已发货", "运输中", "已签收"):
                tracking = f"SF{rng.randint(1000000000, 9999999999)}"

            orders.append(Order(
                id=f"#{datetime.now().year}{rng.randint(100000, 999999)}",
                amount=round(rng.uniform(29, 2999), 0),
                status=status,
                created_at=date,
                items=rng.choice(self._ITEMS),
                tracking=tracking,
            ))

        orders.sort(key=lambda o: o.created_at, reverse=True)
        self._order_cache[query] = orders
        return orders[:limit]


class RestERPAdapter(ERPAdapter):
    """Generic REST API adapter for real ERP systems."""

    def __init__(self, base_url: str, api_key: str = "", timeout: float = 5) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def get_customer(self, query: str) -> Customer | None:
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._base_url}/customer",
                    params={"q": query},
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                d = resp.json()
                return Customer(
                    id=d.get("id", query),
                    name=d.get("name"),
                    phone=d.get("phone"),
                    registered_at=d.get("registered_at"),
                    level=d.get("level"),
                    total_spent=d.get("total_spent", 0),
                    order_count=d.get("order_count", 0),
                    tags=d.get("tags", []),
                    extra=d.get("extra", {}),
                )
        except Exception as e:
            logger.error("ERP customer query failed: %s", e)
            return None

    async def get_orders(self, query: str, limit: int = 5) -> list[Order]:
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._base_url}/orders",
                    params={"q": query, "limit": limit},
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                items = resp.json()
                if isinstance(items, dict):
                    items = items.get("orders", items.get("data", []))
                return [
                    Order(
                        id=o.get("id", ""),
                        amount=o.get("amount", 0),
                        status=o.get("status", ""),
                        created_at=o.get("created_at", ""),
                        items=o.get("items", ""),
                        tracking=o.get("tracking", ""),
                    )
                    for o in items
                ]
        except Exception as e:
            logger.error("ERP order query failed: %s", e)
            return []


def create_erp_adapter() -> ERPAdapter:
    """Factory — create the configured ERP adapter."""
    backend = os.environ.get("CS_ERP_BACKEND", "mock").lower()

    if backend == "rest":
        base_url = os.environ.get("CS_ERP_BASE_URL", "")
        if not base_url:
            logger.warning("CS_ERP_BACKEND=rest but CS_ERP_BASE_URL not set, falling back to mock")
            return MockERPAdapter()
        return RestERPAdapter(
            base_url=base_url,
            api_key=os.environ.get("CS_ERP_API_KEY", ""),
            timeout=float(os.environ.get("CS_ERP_TIMEOUT", "5")),
        )

    if backend != "mock":
        logger.warning("Unknown ERP backend '%s', using mock", backend)

    return MockERPAdapter()
