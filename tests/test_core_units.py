"""Unit tests for the confirmation ladder, confidence gate, planner and language state."""

import pytest

from app.core.confidence import ConfidenceGate, EXISTS, GateThresholds, MALFORMED
from app.core.intents import IntentClassifier
from app.core.language import LanguageState
from app.core.models import Decision, SlotState
from app.core.planner import QuestionPlanner, StepKind
from app.core.slots import SlotManager

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------ slot ladder


async def test_critical_slot_never_skips_read_back():
    slots = SlotManager([("order_id", True)])
    slots.observe("order_id", "ORD-4471", 1.0, 1, Decision.READ_BACK)
    assert slots.get("order_id").state is SlotState.READ_BACK
    assert not slots.has_confirmed("order_id")

    slots.confirm("order_id")
    assert slots.has_confirmed("order_id")


async def test_non_critical_slot_may_be_accepted_outright():
    slots = SlotManager([("product_name", False)])
    slots.observe("product_name", "blender", 0.95, 1, Decision.ACCEPT)
    assert slots.get("product_name").state is SlotState.CONFIRMED


async def test_reask_does_not_overwrite_a_confirmed_value():
    slots = SlotManager([("order_id", True)])
    slots.observe("order_id", "ORD-4471", 1.0, 1, Decision.READ_BACK)
    slots.confirm("order_id")

    slots.observe("order_id", "ORD-9999", 0.2, 2, Decision.REASK)

    assert slots.get("order_id").value == "ORD-4471"
    assert slots.get("order_id").state is SlotState.CONFIRMED


async def test_correction_drops_back_to_read_back_without_burning_an_attempt():
    slots = SlotManager([("order_id", True)])
    slots.observe("order_id", "ORD-4491", 0.8, 1, Decision.READ_BACK)
    attempts_before = slots.get("order_id").attempts

    slots.correct("order_id", "ORD-4471", turn_id=2)

    slot = slots.get("order_id")
    assert slot.value == "ORD-4471"
    assert slot.state is SlotState.READ_BACK
    assert slot.attempts == attempts_before


# --------------------------------------------------------------- confidence gate


async def test_malformed_value_is_reasked_regardless_of_transcript_confidence():
    gate = ConfidenceGate(patterns={"order_id": r"ORD-\d{4}"})
    verdict = await gate.assess("order_id", "banana", transcript_confidence=1.0)
    assert verdict.decision is Decision.REASK
    assert verdict.plausibility == MALFORMED


async def test_confidently_heard_but_nonexistent_id_is_still_low_confidence():
    """The second signal. A clean transcript of a value that resolves to nothing is
    not something to act on."""
    gate = ConfidenceGate(patterns={"order_id": r"ORD-\d{4}"})

    async def never_found(_value: str) -> float:
        return MALFORMED

    gate.register_validator("order_id", never_found)

    verdict = await gate.assess("order_id", "ORD-9999", transcript_confidence=0.99)
    assert verdict.decision is Decision.REASK


async def test_existing_value_with_good_transcript_still_requires_read_back():
    gate = ConfidenceGate(patterns={"order_id": r"ORD-\d{4}"})

    async def found(_value: str) -> float:
        return EXISTS

    gate.register_validator("order_id", found)

    verdict = await gate.assess("order_id", "ORD-4471", 0.99, critical=True)
    assert verdict.decision is Decision.READ_BACK


async def test_low_transcript_confidence_triggers_reask():
    gate = ConfidenceGate(thresholds=GateThresholds(reask_below=0.55))
    verdict = await gate.assess("issue_description", "mumbled", 0.2, critical=False)
    assert verdict.decision is Decision.REASK


# ---------------------------------------------------------------------- planner


async def test_planner_prioritises_highest_resolving_power():
    slots = SlotManager()
    for f in ("order_id", "phone", "order_date", "product_name"):
        slots.register(f)
    planner = QuestionPlanner(slots)

    step = planner.next_step("damaged_item")
    assert step.kind is StepKind.ASK
    assert step.field == "order_id"  # resolving_power 1.0 beats the alternatives


async def test_planner_reroutes_when_the_primary_field_is_exhausted():
    """The behaviour that matters: a caller who cannot produce an order ID is not
    dead-ended."""
    slots = SlotManager()
    for f in ("order_id", "phone", "order_date", "product_name"):
        slots.register(f)
    planner = QuestionPlanner(slots)

    for turn in range(3):
        slots.observe("order_id", "ORD-0000", 0.3, turn, Decision.REASK)
    assert planner.register_attempt_limit("order_id") is True

    step = planner.next_step("damaged_item")
    assert step.kind is StepKind.ASK
    assert step.field != "order_id"
    assert "order_id" not in step.satisfying_set


async def test_planner_prefers_outstanding_read_back_over_new_questions():
    slots = SlotManager()
    slots.register("order_id")
    slots.observe("order_id", "ORD-4471", 0.9, 1, Decision.READ_BACK)
    planner = QuestionPlanner(slots)

    step = planner.next_step("damaged_item")
    assert step.kind is StepKind.READ_BACK
    assert step.field == "order_id"


async def test_planner_reports_no_viable_path_when_everything_is_exhausted():
    slots = SlotManager()
    for f in ("order_id", "phone", "order_date", "product_name"):
        slots.register(f)
        slots.mark_exhausted(f)
    planner = QuestionPlanner(slots)

    assert planner.next_step("damaged_item").kind is StepKind.NO_VIABLE_PATH


# --------------------------------------------------------------------- language


async def test_detects_hinglish_code_switch_within_one_turn():
    lang = LanguageState()
    reading = lang.observe("mera blender kharab aa gaya, box bhi damaged tha")
    assert reading.language == "hi-IN"
    assert reading.code_switch_in_turn is True


async def test_plain_english_is_not_flagged_as_code_switch():
    lang = LanguageState()
    reading = lang.observe("my order arrived damaged yesterday")
    assert reading.language == "en-IN"
    assert reading.code_switch_in_turn is False


async def test_language_switch_between_turns_is_recorded():
    lang = LanguageState()
    lang.observe("hello, I need some help")
    reading = lang.observe("mujhe refund chahiye")
    assert reading.switched_from == "en-IN"
    assert reading.language == "hi-IN"


async def test_devanagari_is_detected():
    lang = LanguageState()
    assert lang.observe("मेरा ऑर्डर खराब आया").language == "hi-IN"


# ------------------------------------------------------------------ classifier


@pytest.mark.parametrize(
    "utterance,expected",
    [
        ("the blender arrived damaged", "damaged_item"),
        ("mera order abhi tak nahi mila", "not_delivered"),
        ("I want to cancel my order", "cancel_order"),
        ("I got the wrong item", "wrong_item"),
        ("where is my money, refund kab aayega", "refund_status"),
        ("I will sue you", "legal_threat"),
        ("someone made an unauthorised charge", "fraud_chargeback"),
        ("I cannot login to my account", "account_access"),
    ],
)
async def test_rule_classifier_covers_the_taxonomy(utterance, expected):
    result = await IntentClassifier().classify(utterance)
    assert result.intent == expected


async def test_unmatched_utterance_falls_through_to_out_of_scope():
    result = await IntentClassifier().classify("what is the weather like today")
    assert result.intent == "out_of_scope"
