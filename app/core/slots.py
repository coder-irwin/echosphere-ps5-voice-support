"""Slot manager — the confirmation ladder.

    unheard -> heard(confidence) -> read_back -> confirmed

The invariant this module exists to enforce: **a tool call may only read slots in
CONFIRMED state.** The model is never trusted to remember whether it confirmed
something; server-side slot state is the source of truth, which is also what lets
"never repeat yourself" survive a reconnection.
"""

from __future__ import annotations

from typing import Iterable, Optional

from app.core.models import Decision, Slot, SlotObservation, SlotState


class SlotManager:
    def __init__(self, fields: Iterable[tuple[str, bool]] = ()) -> None:
        self._slots: dict[str, Slot] = {}
        for name, critical in fields:
            self.register(name, critical)

    # ------------------------------------------------------------------ registry

    def register(self, field: str, critical: bool = True) -> Slot:
        if field not in self._slots:
            self._slots[field] = Slot(field=field, critical=critical)
        return self._slots[field]

    def get(self, field: str) -> Optional[Slot]:
        return self._slots.get(field)

    def all(self) -> list[Slot]:
        return list(self._slots.values())

    # --------------------------------------------------------------- transitions

    def observe(
        self,
        field: str,
        value: str,
        transcript_confidence: float,
        turn_id: int,
        decision: Decision,
    ) -> Slot:
        """Record a heard value and advance the ladder according to the gate's verdict.

        A REASK does not overwrite an existing confirmed value — a garbled re-hearing
        must never silently undo something the caller already confirmed.
        """
        slot = self.register(field)
        slot.attempts += 1
        slot.observations.append(
            SlotObservation(
                value=value, transcript_confidence=transcript_confidence, turn_id=turn_id
            )
        )

        if decision is Decision.REASK:
            if slot.state is not SlotState.CONFIRMED:
                slot.state = SlotState.HEARD
                slot.value = value
                slot.confidence = transcript_confidence
            return slot

        slot.value = value
        slot.confidence = transcript_confidence

        if decision is Decision.ACCEPT and not slot.critical:
            slot.state = SlotState.CONFIRMED
        else:
            slot.state = SlotState.READ_BACK

        return slot

    def confirm(self, field: str) -> Slot:
        """Caller said yes to a read-back."""
        slot = self.register(field)
        if slot.value is None:
            raise ValueError(f"cannot confirm {field!r} with no observed value")
        slot.state = SlotState.CONFIRMED
        return slot

    def correct(self, field: str, value: str, turn_id: int, confidence: float = 1.0) -> Slot:
        """Caller corrected a value mid-readback — 'no, seven, not nine'.

        A correction always drops back to READ_BACK: the corrected value must itself be
        read back and confirmed. Attempts are not incremented, because the caller
        supplying a correction is cooperation, not failure, and should not push the slot
        toward exhaustion.
        """
        slot = self.register(field)
        slot.observations.append(
            SlotObservation(value=value, transcript_confidence=confidence, turn_id=turn_id)
        )
        slot.value = value
        slot.confidence = confidence
        slot.state = SlotState.READ_BACK
        slot.exhausted = False
        return slot

    def mark_exhausted(self, field: str) -> Slot:
        """Too many failed attempts — the planner should route around this field."""
        slot = self.register(field)
        slot.exhausted = True
        return slot

    def reset(self, field: str) -> Slot:
        slot = self.register(field)
        slot.state = SlotState.UNHEARD
        slot.value = None
        slot.confidence = 0.0
        return slot

    # ----------------------------------------------------------------- accessors

    def confirmed(self) -> dict[str, str]:
        return {
            s.field: s.value
            for s in self._slots.values()
            if s.is_confirmed and s.value is not None
        }

    def unconfirmed(self) -> dict[str, Optional[str]]:
        return {s.field: s.value for s in self._slots.values() if not s.is_confirmed}

    def has_confirmed(self, *fields: str) -> bool:
        return all(
            (s := self._slots.get(f)) is not None and s.is_confirmed for f in fields
        )

    def missing_from(self, fields: Iterable[str]) -> list[str]:
        """Which of these fields are not yet confirmed."""
        return [f for f in fields if not self.has_confirmed(f)]

    def snapshot(self) -> list[dict]:
        """Panel-friendly view. Drives the slot board."""
        return [
            {
                "field": s.field,
                "state": s.state.value,
                "value": s.value,
                "confidence": round(s.confidence, 3),
                "attempts": s.attempts,
                "critical": s.critical,
                "exhausted": s.exhausted,
            }
            for s in self._slots.values()
        ]
