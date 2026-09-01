# Case coverage map

**Organising principle:** breadth is cheap, depth is expensive, and cross-cutting behaviour
is what actually scores.

ShopWave's rule engine classifies in O(1) with LLM fallback for nuance — so *recognising* an
intent costs an entry in a table. *Resolving* one costs slots, policy rules, tools and test
cases. Spend accordingly.

---

## Tier 1 — Hero flows (full depth, demo path)

Every UX mechanism runs: slot manager, confirmation ladder, confidence gating, policy
adjudication, tool execution, warm escalation.

| Flow | Why it earns the depth |
|---|---|
| **Damaged / defective on arrival** | The hero. Emotional, high-value, naturally crosses the refund threshold → forces a visible policy block. |
| **Not delivered / marked delivered but missing** | Highest-frequency real complaint. Investigation branch, not a simple lookup. |
| **Return & refund request** | Return-window policy engine already built. Eligibility refusal is audible and defensible. |
| **Cancel order** | State-dependent — pre-dispatch vs post-dispatch gives two genuinely different outcomes from one intent. |
| **Wrong item received** | Exchange path; exercises idempotency and identity verification. |

## Tier 2 — Complete but lighter (built and tested, off the demo path)

Nine more intents that resolve end-to-end, reusing Tier 1's machinery with thinner slot
sets. Cheap because the hard parts are shared.

1. Order status / tracking
2. Address change before dispatch
3. Size or colour exchange
4. Refund status — *"where is my money"*
5. Payment debited but order failed
6. Warranty triage
7. Promo code not applied
8. Subscription pause / cancel
9. Invoice request

## Tier 3 — Recognised and routed, deliberately not resolved

1. Account access / login issues
2. Fraud or chargeback claims
3. Seller / marketplace disputes
4. Bulk & B2B orders
5. Legal threats
6. Delivery-agent complaints
7. Restock enquiries
8. Policy & store questions
9. Anything out of scope

**The distinction that matters:** ShopWave's original thesis was that support AI fails by
bouncing ~80% of *actionable* tickets back to humans. So Tier 3 escalation must read as
**policy, not incapacity** — and the transparency panel labels it exactly that way:

- 🟦 **"Escalated by design"** — this class of case is defined as requiring human judgement
- 🟨 **"Escalated due to low confidence"** — the agent tried and wasn't sure enough

Two different colours. Judges will notice, and it reframes the escalation rate as a design
position rather than a failure metric.

---

## Cross-cutting behaviours — what actually wins

These apply across every tier and are worth more than twenty extra intents.

| # | Behaviour | Maps to PS5 requirement |
|---|---|---|
| 1 | Interrupting the agent mid-sentence | 2 — natural interruption handling |
| 2 | Correcting an already-confirmed value — *"no, seven, not nine"* | 4 — repetition & confirmation |
| 3 | Switching topic and returning to an earlier one | Contextual memory (universal req.) |
| 4 | Code-switching mid-sentence | 1 — multilingual & code-switched |
| 5 | Noise burst or silence during a critical field | 7 — background-noise resilience |
| 6 | Asking for something out of bounds → spoken refusal | 10 — clear boundaries |
| 7 | Disputing the agent's decision → escalation | 8 — human escalation |
| 8 | Unable to supply a required field → question flow re-plans | 6 — prioritized question flow |
| 9 | Raising two separate issues in one call | 3 — information collection |

**A team demoing thirty shallow intents loses to a team demoing five flows that survive all
nine of these.** That is the bet this project is making.

---

## Guardrail catalogue

PS5 requirement 10 — "clear boundaries around what the AI is allowed to do". Ours are
enforced **in code, not prompt**. Each one is a logged, deterministic decision.

| # | Guardrail | Enforcement |
|---|---|---|
| 1 | No autonomous refund above the value threshold | Hard cutoff in policy engine |
| 2 | No refund outside the return window — *states which rule fired* | Policy engine, date check |
| 3 | No action on unverified identity | Slot manager: identity slots must be `confirmed` |
| 4 | No duplicate refund | Idempotency check on `refund_status` |
| 5 | No legal or financial advice presented as authoritative | Refusal + escalate |
| 6 | No delivery promises it cannot verify | Tool-grounded answers only |
| 7 | No product health or medical claims | Refusal |
| 8 | Social-engineering / invented-policy detection | Fraud detector → escalate |
| 9 | AI disclosure at call open, and again on request | System instruction + audit assertion |

### Mapping to PS5's explicit safety restrictions

| PS5 says the prototype must NOT | Covered by |
|---|---|
| Provide medical diagnosis | Guardrail 7 |
| Replace trained emergency responders | Out of scope by domain; Tier 3 routing |
| Provide legal/financial/emergency instructions as authoritative advice | Guardrail 5 |
| Present uncertain AI output as confirmed fact | Confidence gate + guardrail 6 |

---

## The honest scoreboard

> **23 intents recognised · 14 resolved end-to-end · 9 guardrails enforced in code ·
> 9 conversational behaviours handled**

Stronger than claiming "30 intents", because every number survives questioning.

---

## Cut list, in order

If the sprint runs behind, drop Tier 2 from the bottom up:

1. Invoice request
2. Subscription pause / cancel
3. Promo code not applied
4. Warranty triage

**Never cut a cross-cutting behaviour to save an intent.** Breadth is what judges forgive.
A demo where the agent can't handle being interrupted is what they don't.
