"""E-commerce tools.

Carried over from ShopWave's `tools/resolution_tools.py` and adapted: the tools no longer
decide anything. `issue_refund` here simply issues a refund — whether it is *allowed* to
is the policy engine's job, adjudicated before this is ever called.

That separation is deliberate. When the same object both performs an action and decides
whether the action is permitted, the guarantee is only as strong as the discipline of
whoever calls it next.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Any, Optional

from app.tools.data import DataStore


class EcommerceTools:
    def __init__(self, store: DataStore, latency_ms: tuple[int, int] = (40, 160)) -> None:
        self.store = store
        self._latency = latency_ms
        self.refund_log: list[dict] = []

    async def _io(self) -> None:
        """Simulated network latency so the panel's latency numbers mean something."""
        low, high = self._latency
        await asyncio.sleep(random.uniform(low, high) / 1000)

    # ------------------------------------------------------------------ reads

    async def get_order(self, order_id: str) -> dict[str, Any]:
        await self._io()
        order = self.store.order(order_id)
        if not order:
            return {"error": "order_not_found", "order_id": order_id}
        product = self.store.product(order["product_id"]) or {}
        return {
            **{k: v for k, v in order.items() if k != "notes"},
            "product_name": product.get("name"),
        }

    async def get_customer(
        self, phone: Optional[str] = None, email: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> dict[str, Any]:
        await self._io()
        customer = None
        if customer_id:
            customer = self.store.customer(customer_id)
        elif phone:
            customer = self.store.customer_by_phone(phone)
        elif email:
            customer = self.store.customer_by_email(email)
        if not customer:
            return {"error": "customer_not_found"}
        return {k: v for k, v in customer.items() if k not in {"notes", "address"}}

    async def get_product(self, product_id: str) -> dict[str, Any]:
        await self._io()
        product = self.store.product(product_id)
        if not product:
            return {"error": "product_not_found", "product_id": product_id}
        return {k: v for k, v in product.items() if k != "notes"}

    async def search_knowledge_base(self, query: str) -> dict[str, Any]:
        await self._io()
        sections = self.store.search_knowledge_base(query)
        if not sections:
            return {"found": False, "sections": [], "note": "No matching policy section."}
        return {"found": True, "sections": sections}

    async def check_refund_eligibility(self, order_id: str) -> dict[str, Any]:
        """Reports state. Does not authorise anything — see the module docstring."""
        await self._io()
        order = self.store.order(order_id)
        if not order:
            return {"eligible": False, "reason": "order_not_found"}
        product = self.store.product(order["product_id"]) or {}
        return {
            "order_id": order["order_id"],
            "amount": order["amount"],
            "already_refunded": order.get("refund_status") == "refunded",
            "return_deadline": order.get("return_deadline"),
            "returnable_category": product.get("returnable", False),
            "status": order.get("status"),
        }

    # ----------------------------------------------------------------- writes

    async def issue_refund(self, order_id: str, amount: float) -> dict[str, Any]:
        await self._io()
        order = self.store.order(order_id)
        if not order:
            return {"success": False, "error": "order_not_found"}
        if order.get("refund_status") == "refunded":
            # Defence in depth: policy blocks this first, but a write path should never
            # rely solely on its caller having checked.
            return {"success": False, "error": "already_refunded"}

        order["refund_status"] = "refunded"
        ref = f"REF-{order_id}-{int(datetime.now(timezone.utc).timestamp())}"
        self.refund_log.append({"order_id": order_id, "amount": amount, "reference": ref})
        return {"success": True, "reference": ref, "amount": amount, "order_id": order_id}

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        await self._io()
        order = self.store.order(order_id)
        if not order:
            return {"success": False, "error": "order_not_found"}
        order["status"] = "cancelled"
        return {"success": True, "order_id": order_id, "status": "cancelled"}

    async def create_replacement(self, order_id: str) -> dict[str, Any]:
        await self._io()
        order = self.store.order(order_id)
        if not order:
            return {"success": False, "error": "order_not_found"}
        return {
            "success": True,
            "order_id": order_id,
            "replacement_id": f"RPL-{order_id}",
            "eta_days": 4,
        }

    async def update_address(self, order_id: str, new_address: str) -> dict[str, Any]:
        await self._io()
        order = self.store.order(order_id)
        if not order:
            return {"success": False, "error": "order_not_found"}
        if order.get("status") != "processing":
            return {"success": False, "error": "already_dispatched"}
        order["delivery_address"] = new_address
        return {"success": True, "order_id": order_id, "new_address": new_address}

    async def send_invoice(self, order_id: str) -> dict[str, Any]:
        await self._io()
        if not self.store.order(order_id):
            return {"success": False, "error": "order_not_found"}
        return {"success": True, "order_id": order_id, "sent_to": "registered email"}
