"""Language state — track what the caller is speaking and mirror it.

Two things matter here that a plain "detect language" call does not give you:

  1. **Code-switching within a single turn.** "blender kharab aa gaya, box bhi damaged
     tha" is one utterance in two languages. Detecting only a dominant language loses
     the thing PS5 is actually asking about.
  2. **Entity values stay language-neutral.** An order ID is an order ID regardless of
     the sentence around it, so slot values are never translated.

The model (Gemini Live) supplies a language hint per turn where it can; this module
corroborates it with script and lexical evidence so the panel can show a code-switch
marker even when the hint is a single label.
"""

from __future__ import annotations

import re
from typing import Optional

from app.core.models import LanguageReading

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN = re.compile(r"[A-Za-z]")

# Romanised Hindi markers. Deliberately function words and high-frequency verbs — content
# words are where Hinglish speakers borrow English, so they are poor language evidence.
ROMANISED_HINDI = {
    "hai", "hain", "nahi", "nahin", "kya", "mera", "meri", "mujhe", "aapka", "aap",
    "kar", "karna", "kiya", "gaya", "gayi", "raha", "rahi", "tha", "thi", "bhi",
    "kab", "kaise", "kitna", "kitne", "kyun", "abhi", "phir", "lekin", "aur", "wapas",
    "paisa", "paise", "acha", "theek", "haan", "ji", "bhaiya", "sir",
}

DEFAULT_LANGUAGE = "en-IN"
HINDI = "hi-IN"
ENGLISH = "en-IN"


class LanguageState:
    def __init__(self, default: str = DEFAULT_LANGUAGE) -> None:
        self._current = default
        self._history: list[LanguageReading] = []

    @property
    def current(self) -> str:
        return self._current

    @property
    def history(self) -> list[LanguageReading]:
        return list(self._history)

    def observe(self, text: str, hint: Optional[str] = None) -> LanguageReading:
        detected, mixed = self._detect(text)
        language = hint or detected or self._current

        switched_from = self._current if language != self._current else None
        reading = LanguageReading(
            language=language,
            switched_from=switched_from,
            code_switch_in_turn=mixed,
        )
        self._current = language
        self._history.append(reading)
        return reading

    def _detect(self, text: str) -> tuple[Optional[str], bool]:
        if not text or not text.strip():
            return None, False

        has_devanagari = bool(DEVANAGARI.search(text))
        words = re.findall(r"[A-Za-z']+", text.lower())
        hindi_words = {w for w in words if w in ROMANISED_HINDI}
        english_words = [w for w in words if w not in ROMANISED_HINDI]

        hindi_evidence = has_devanagari or bool(hindi_words)
        english_evidence = bool(english_words) and bool(LATIN.search(text))

        mixed = hindi_evidence and english_evidence and len(english_words) >= 1

        if has_devanagari and english_evidence:
            return HINDI, True
        if hindi_evidence and not english_evidence:
            return HINDI, False
        if hindi_evidence and english_evidence:
            # Hinglish. Function words carry the grammatical frame, so attribute the turn
            # to Hindi and flag the switch rather than calling it English with loanwords.
            return HINDI, True
        if english_evidence:
            return ENGLISH, False
        return None, False

    def snapshot(self) -> dict:
        last = self._history[-1] if self._history else None
        return {
            "current": self._current,
            "switched_from": last.switched_from if last else None,
            "code_switch_in_turn": last.code_switch_in_turn if last else False,
            "turns_observed": len(self._history),
        }
