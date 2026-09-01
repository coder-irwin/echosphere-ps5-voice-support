"""Entity extraction and confirmation detection.

Slots are driven from what the caller actually said, not from what the model reports
having understood. That matters: if the model is the one telling us a value was confirmed,
the confirmation ladder guarantees nothing — it becomes another thing a prompt can be
talked out of.

Spoken digits are handled in both English and Hindi, because callers read order numbers
aloud one digit at a time and rarely in the language of the surrounding sentence.
"""

from __future__ import annotations

import re
from typing import Optional

ORDER_ID = re.compile(r"\bORD[\s-]?(\d{4})\b", re.I)
EMAIL = re.compile(r"\b[^@\s]+@[^@\s]+\.\w{2,}\b")
PHONE = re.compile(r"(?:\+?91[\s-]?)?\b(\d{5}[\s-]?\d{5}|\d{10})\b")

DIGIT_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "shunya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4",
    "paanch": "5", "panch": "5", "chah": "6", "chhe": "6", "saat": "7",
    "aath": "8", "nau": "9",
}

AFFIRM = {
    "yes", "yeah", "yep", "correct", "right", "that's right", "thats right",
    "haan", "han", "ji", "ji haan", "bilkul", "sahi", "theek", "thik hai", "ok", "okay",
}
NEGATE = {
    "no", "nope", "not right", "wrong", "incorrect", "nahi", "nahin", "galat", "nai",
}


def extract_order_id(text: str) -> Optional[str]:
    match = ORDER_ID.search(text or "")
    if match:
        return f"ORD-{match.group(1)}"
    # "order number four four seven one"
    digits = spoken_digits(text)
    if len(digits) == 4:
        return f"ORD-{digits}"
    return None


def extract_phone(text: str) -> Optional[str]:
    match = PHONE.search(text or "")
    if match:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) >= 10:
            return f"+91-{digits[-10:-5]}-{digits[-5:]}"
    return None


def extract_email(text: str) -> Optional[str]:
    match = EMAIL.search(text or "")
    return match.group(0).lower() if match else None


def spoken_digits(text: str) -> str:
    """Pull a run of spoken digits out of an utterance, in English or Hindi."""
    tokens = re.findall(r"[a-z']+|\d", (text or "").lower())
    digits: list[str] = []
    for token in tokens:
        if token.isdigit():
            digits.append(token)
        elif token in DIGIT_WORDS:
            digits.append(DIGIT_WORDS[token])
        elif digits:
            # A non-digit word breaks the run; keep the longest run seen so far.
            break
    return "".join(digits)


def is_affirmation(text: str) -> bool:
    lowered = _normalise(text)
    return any(lowered == a or lowered.startswith(a + " ") for a in AFFIRM)


def is_negation(text: str) -> bool:
    lowered = _normalise(text)
    return any(word in lowered.split() for word in NEGATE) or lowered.startswith("nahi")


def extract_all(text: str) -> dict[str, str]:
    """Everything identifiable in one utterance."""
    found: dict[str, str] = {}
    if (order_id := extract_order_id(text)):
        found["order_id"] = order_id
    if (phone := extract_phone(text)):
        found["phone"] = phone
    if (email := extract_email(text)):
        found["email"] = email
    return found


def _normalise(text: str) -> str:
    return re.sub(r"[^\w\s]", "", (text or "").strip().lower())
