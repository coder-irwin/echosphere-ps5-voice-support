"""In-memory store over the demo JSON fixtures.

Adapted from ShopWave's `services/data_service.py`. Kept deliberately simple — this is a
prototype's system of record, and swapping it for Postgres is a stated future improvement
rather than something to half-build now.

`reset()` exists because the single most common demo-day failure is running the hero flow
against an order that a previous rehearsal already refunded.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class DataStore:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self._pristine: dict[str, Any] = {}
        self.customers: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}
        self.products: dict[str, dict] = {}
        self.knowledge_base: str = ""
        self.load()

    def load(self) -> None:
        self._pristine = {
            "customers": self._read("customers.json"),
            "orders": self._read("orders.json"),
            "products": self._read("products.json"),
        }
        self.knowledge_base = (self.data_dir / "knowledge-base.md").read_text(encoding="utf-8")
        self.reset()

    def reset(self) -> None:
        """Restore mutable state. Run this between demo takes."""
        data = copy.deepcopy(self._pristine)
        self.customers = {c["customer_id"]: c for c in data["customers"]}
        self.orders = {o["order_id"]: o for o in data["orders"]}
        self.products = {p["product_id"]: p for p in data["products"]}

    def _read(self, name: str) -> list[dict]:
        return json.loads((self.data_dir / name).read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- lookups

    def order(self, order_id: str) -> Optional[dict]:
        return self.orders.get((order_id or "").strip().upper())

    def customer(self, customer_id: str) -> Optional[dict]:
        return self.customers.get(customer_id)

    def product(self, product_id: str) -> Optional[dict]:
        return self.products.get(product_id)

    def customer_by_phone(self, phone: str) -> Optional[dict]:
        digits = _digits(phone)
        if len(digits) < 8:
            return None
        for c in self.customers.values():
            if _digits(c["phone"]).endswith(digits[-10:]):
                return c
        return None

    def customer_by_email(self, email: str) -> Optional[dict]:
        target = (email or "").strip().lower()
        for c in self.customers.values():
            if c["email"].lower() == target:
                return c
        return None

    def orders_for_customer(self, customer_id: str) -> list[dict]:
        return [o for o in self.orders.values() if o["customer_id"] == customer_id]

    def search_knowledge_base(self, query: str, limit: int = 2) -> list[dict[str, str]]:
        """Keyword section match. Returns sections verbatim so answers stay grounded."""
        terms = [t for t in (query or "").lower().split() if len(t) > 3]
        matches = []
        for block in self.knowledge_base.split("\n## ")[1:]:
            heading, _, body = block.partition("\n")
            score = sum(1 for t in terms if t in block.lower())
            if score:
                matches.append({"section": heading.strip(), "text": body.strip(), "_score": score})
        matches.sort(key=lambda m: -m["_score"])
        return [{k: v for k, v in m.items() if k != "_score"} for m in matches[:limit]]


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())
