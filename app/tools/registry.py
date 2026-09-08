"""Tool registry — declarations and dispatch.

One source of truth for the tool schema, emitted in both the OpenAI function format (for
the cascade adapter) and the Gemini function-declaration format (for the MLLM bridge).
Keeping one definition and two projections is what stops the two transport paths from
drifting apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.tools.ecommerce import EcommerceTools
from app.tools.ticketing import TicketingService


@dataclass(frozen=True)
class ToolDecl:
    name: str
    description: str
    properties: dict[str, dict[str, Any]] = field(default_factory=dict)
    required: tuple[str, ...] = ()

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": list(self.required),
                },
            },
        }

    def to_gemini(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    k: {**v, "type": v["type"].upper()} for k, v in self.properties.items()
                },
                "required": list(self.required),
            },
        }


_STR = {"type": "string"}
_NUM = {"type": "number"}

DECLARATIONS: tuple[ToolDecl, ...] = (
    ToolDecl(
        "get_order",
        "Look up an order by its confirmed order ID. Call only after the caller has "
        "confirmed the order ID back to you.",
        {"order_id": {**_STR, "description": "Order ID in the form ORD-1234"}},
        ("order_id",),
    ),
    ToolDecl(
        "get_customer",
        "Look up the customer by registered phone or email, to verify identity.",
        {"phone": _STR, "email": _STR},
    ),
    ToolDecl(
        "get_product",
        "Look up product details including warranty and whether the category is returnable.",
        {"product_id": _STR},
        ("product_id",),
    ),
    ToolDecl(
        "check_refund_eligibility",
        "Report the refund-relevant state of an order. This reports facts; it does not "
        "authorise a refund.",
        {"order_id": _STR},
        ("order_id",),
    ),
    ToolDecl(
        "search_knowledge_base",
        "Search published support policy. Use this rather than answering policy questions "
        "from memory.",
        {"query": _STR},
        ("query",),
    ),
    ToolDecl(
        "issue_refund",
        "Issue a refund for a confirmed order. May be blocked by policy — if it is, tell "
        "the caller plainly and do not imply the refund will happen.",
        {"order_id": _STR, "amount": _NUM},
        ("order_id", "amount"),
    ),
    ToolDecl(
        "cancel_order",
        "Cancel an order that is still processing.",
        {"order_id": _STR},
        ("order_id",),
    ),
    ToolDecl(
        "create_replacement",
        "Create a replacement shipment for a confirmed order.",
        {"order_id": _STR},
        ("order_id",),
    ),
    ToolDecl(
        "update_address",
        "Change the delivery address of an order that has not yet dispatched.",
        {"order_id": _STR, "new_address": _STR},
        ("order_id", "new_address"),
    ),
    ToolDecl(
        "send_invoice",
        "Email the invoice for an order to the registered address.",
        {"order_id": _STR},
        ("order_id",),
    ),
    ToolDecl(
        "escalate",
        "Hand the call to a human colleague. Use when the caller asks, when confidence is "
        "low, or when policy blocks what they need.",
        {"reason": _STR},
        ("reason",),
    ),
    ToolDecl(
        "report_slot",
        "Record a detail the caller just stated — an order_id, phone, email, new_address, "
        "order_date or product_name — before you have read it back. Call this every time "
        "you hear a new value for one of these fields, even if you have not confirmed it "
        "yet. This does not authorise anything by itself.",
        {"field": _STR, "value": _STR},
        ("field", "value"),
    ),
    ToolDecl(
        "confirm_slot",
        "Call this only immediately after you have read a value back to the caller — "
        "digit by digit for identifiers — and they have explicitly agreed it is correct. "
        "Always pass the exact value they confirmed, even if you already called "
        "report_slot for it earlier. Never call this without an explicit yes from the "
        "caller.",
        {"field": _STR, "value": _STR},
        ("field", "value"),
    ),
)

# Bookkeeping tools the orchestrator routes straight to the slot ladder rather than
# through CallSession.propose_action — they track what the caller said, they never act.
SLOT_TOOLS = frozenset({"report_slot", "confirm_slot"})

BY_NAME = {d.name: d for d in DECLARATIONS}


def openai_tools() -> list[dict[str, Any]]:
    return [d.to_openai() for d in DECLARATIONS]


def gemini_tools() -> list[dict[str, Any]]:
    return [{"function_declarations": [d.to_gemini() for d in DECLARATIONS]}]


class ToolRunner:
    """Dispatches a tool call to its implementation.

    Deliberately dumb: no policy, no slot checks, no decisions. Everything that adjudicates
    happens in `CallSession.propose_action` before this is reached.
    """

    def __init__(
        self,
        ecommerce: EcommerceTools,
        ticketing: Optional[TicketingService] = None,
        on_escalate: Optional[Callable[[str], Awaitable[dict[str, Any]]]] = None,
    ) -> None:
        self.ecommerce = ecommerce
        self.ticketing = ticketing or TicketingService()
        self._on_escalate = on_escalate

    async def __call__(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "escalate":
            if self._on_escalate is None:
                return {"success": True, "note": "escalation handled by session"}
            return await self._on_escalate(args.get("reason", "unspecified"))

        impl = getattr(self.ecommerce, name, None)
        if impl is None:
            return {"error": "unknown_tool", "tool": name}

        decl = BY_NAME.get(name)
        if decl is not None:
            missing = [r for r in decl.required if args.get(r) in (None, "")]
            if missing:
                return {"error": "missing_arguments", "missing": missing}
            args = {k: v for k, v in args.items() if k in decl.properties}

        return await impl(**args)
