"""Confidence gate.

Low-confidence detection uses **two** signals, not one:

  1. transcript confidence — how well was it heard
  2. semantic plausibility — does this value actually mean anything in our system

The second is what makes this real rather than a prompt instruction. A confidently
transcribed but nonexistent order ID is still low confidence for our purposes, and the
agent should re-ask rather than proceed to a tool call that will fail.

The enforced invariant: **a critical field never reaches CONFIRMED without a read-back.**
No transcript confidence, however high, can skip the ladder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from app.core.models import ConfidenceVerdict, Decision

# plausibility levels
EXISTS = 1.0
WELL_FORMED = 0.5
MALFORMED = 0.0

Validator = Callable[[str], Awaitable[float]]


@dataclass(frozen=True)
class GateThresholds:
    reask_below: float = 0.55
    accept_above: float = 0.85
    transcript_weight: float = 0.6

    @property
    def plausibility_weight(self) -> float:
        return 1.0 - self.transcript_weight


class ConfidenceGate:
    def __init__(
        self,
        thresholds: GateThresholds | None = None,
        patterns: Optional[dict[str, str]] = None,
        validators: Optional[dict[str, Validator]] = None,
    ) -> None:
        self.t = thresholds or GateThresholds()
        self._patterns = {k: re.compile(v, re.I) for k, v in (patterns or {}).items()}
        self._validators = validators or {}

    def register_validator(self, field: str, validator: Validator) -> None:
        """Existence check — e.g. does this order ID resolve to a real order."""
        self._validators[field] = validator

    async def assess(
        self,
        field: str,
        value: str,
        transcript_confidence: float,
        critical: bool = True,
    ) -> ConfidenceVerdict:
        plausibility, reason = await self._plausibility(field, value)

        combined = (
            self.t.transcript_weight * transcript_confidence
            + self.t.plausibility_weight * plausibility
        )

        if plausibility == MALFORMED:
            decision = Decision.REASK
        elif combined < self.t.reask_below:
            decision = Decision.REASK
            reason = reason or "combined confidence below re-ask threshold"
        elif critical:
            # No shortcut exists here, and that is deliberate.
            decision = Decision.READ_BACK
            reason = reason or "critical field — read-back required"
        elif combined >= self.t.accept_above:
            decision = Decision.ACCEPT
            reason = reason or "high confidence, non-critical field"
        else:
            decision = Decision.READ_BACK
            reason = reason or "moderate confidence — confirming"

        return ConfidenceVerdict(
            field=field,
            value=value,
            transcript_confidence=round(transcript_confidence, 3),
            plausibility=plausibility,
            combined=round(combined, 3),
            decision=decision,
            reason=reason,
        )

    async def _plausibility(self, field: str, value: str) -> tuple[float, str]:
        value = (value or "").strip()
        if not value:
            return MALFORMED, "empty value"

        pattern = self._patterns.get(field)
        if pattern and not pattern.fullmatch(value):
            return MALFORMED, f"does not match expected format for {field}"

        validator = self._validators.get(field)
        if validator is None:
            return WELL_FORMED, "well-formed, existence not checkable"

        score = await validator(value)
        if score <= MALFORMED:
            return MALFORMED, f"no record matches this {field}"
        return score, "resolved against system of record" if score >= EXISTS else "partial match"
