"""Prioritised question planner.

PS5 requirement 6. Most implementations hardcode a question sequence; this one picks
whichever field most reduces remaining uncertainty, and — the part that actually matters —
**re-plans around a field the caller cannot produce.**

An intent declares alternative satisfying sets, e.g. for a refund:

    (("order_id",), ("phone", "order_date", "product_name"))

If `order_id` exhausts its attempts, that whole set becomes unusable and the planner
switches to the phone/date/product path rather than dead-ending on the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.core.intents import FIELDS, required_fields
from app.core.models import SlotState
from app.core.slots import SlotManager


class StepKind(str, Enum):
    READ_BACK = "read_back"
    ASK = "ask"
    PROCEED = "proceed"
    NO_VIABLE_PATH = "no_viable_path"


@dataclass
class NextStep:
    kind: StepKind
    field: Optional[str] = None
    reason: str = ""
    satisfying_set: tuple[str, ...] = ()


class QuestionPlanner:
    def __init__(self, slots: SlotManager) -> None:
        self.slots = slots

    def next_step(self, intent: str) -> NextStep:
        # 1. An outstanding read-back always wins. Never stack a new question on top of
        #    a value the caller has not yet confirmed.
        for slot in self.slots.all():
            if slot.state is SlotState.READ_BACK:
                return NextStep(
                    StepKind.READ_BACK,
                    slot.field,
                    "value heard but not yet confirmed",
                )

        sets = required_fields(intent)
        if not sets:
            return NextStep(StepKind.PROCEED, reason="intent requires no slots")

        viable = [s for s in sets if self._is_viable(s)]
        if not viable:
            return NextStep(
                StepKind.NO_VIABLE_PATH,
                reason="every identification path is exhausted",
            )

        # 2. Cheapest-to-complete path, breaking ties toward the more informative one.
        best = min(
            viable,
            key=lambda s: (
                len(self.slots.missing_from(s)),
                -sum(FIELDS[f].resolving_power for f in s if f in FIELDS),
            ),
        )

        missing = self.slots.missing_from(best)
        if not missing:
            return NextStep(StepKind.PROCEED, satisfying_set=best, reason="all required slots confirmed")

        # 3. Within the chosen path, ask whatever removes the most uncertainty.
        field = max(missing, key=lambda f: FIELDS[f].resolving_power if f in FIELDS else 0.0)
        return NextStep(
            StepKind.ASK,
            field,
            f"highest resolving power among {missing}",
            satisfying_set=best,
        )

    def register_attempt_limit(self, field: str) -> bool:
        """Mark a field exhausted if it has burned through its attempts.

        Returns True when the field was newly exhausted, so the caller can log the
        re-plan as an event rather than silently changing course.
        """
        slot = self.slots.get(field)
        spec = FIELDS.get(field)
        if slot is None or spec is None or slot.exhausted:
            return False
        if slot.state is not SlotState.CONFIRMED and slot.attempts >= spec.max_attempts:
            self.slots.mark_exhausted(field)
            return True
        return False

    def _is_viable(self, satisfying_set: tuple[str, ...]) -> bool:
        for f in satisfying_set:
            slot = self.slots.get(f)
            if slot is not None and slot.exhausted and not slot.is_confirmed:
                return False
        return True
