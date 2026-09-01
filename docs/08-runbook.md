# Runbook — evaluation day and finale

Two live events. **5–6 Sep online evaluation** (no modifications permitted) and
**12 Sep Grand Finale** in Delhi. This is the operational checklist for both.

---

## T-minus checklist

### Before 4 Sep 23:59 IST (submission deadline)

- [x] Prototype deployed and publicly reachable — **not localhost** — see [docs/09-deployment.md](09-deployment.md)
- [x] Repo public, README complete, architecture diagram committed — [github.com/coder-irwin/echosphere-ps5-voice-support](https://github.com/coder-irwin/echosphere-ps5-voice-support), diagram in [docs/02-architecture.md](02-architecture.md)
- [ ] 3–5 minute demo video recorded and uploaded
- [x] Technologies list and known-limitations doc in the repo — [docs/09-deployment.md](09-deployment.md)
- [x] `.env.example` complete; no real secrets committed
- [x] Smoke test from a **different network** than the dev machine — health, session, message, and the `wss://` transparency panel all verified live against the Cloud Run URL
- [ ] Tag the submission commit — after this, no changes are permitted

### Morning of a live demo

- [ ] Deployment healthy — hit `/health`, check the panel loads
- [ ] Agora credentials valid, token generation working
- [ ] Gemini API key has quota remaining
- [ ] Ticketing sandbox reachable; create and delete one test ticket
- [ ] Demo data reset to clean state (`ORD-4471` **not** already refunded — idempotency will
      block the hero beat if you forget this)
- [ ] Audio devices selected on every machine; test the caller mic
- [ ] Full dry run, end to end, timed
- [ ] Backup recording queued and ready to play
- [ ] Everyone knows their role and their failure cue

**The single most common demo-day failure: forgetting to reset the order state.** Put it at
the top of the list for a reason.

---

## Roles during the demo

| Role | Primary job | Failure job |
|---|---|---|
| Caller | Runs the script | Keep talking naturally; do not freeze if the agent misbehaves |
| Console operator | Joins, approves | Announce the escalation verbally if the console lags |
| Narrator | Reads the panel aloud | Bridge any dead air; never say "it's usually faster than this" |
| Ops | Silent monitoring | Execute the failure procedures below |

---

## Failure procedures

### Agent doesn't join the channel
1. Ops restarts the agent via the console's **Restart agent** control.
2. Narrator covers with the architecture explanation — this is a natural 30-second gap filler.
3. If it fails twice, switch to the backup recording and continue narrating live.

### Agent joins but doesn't respond
Usually a Gemini quota or key issue. Check the panel — if transcripts are streaming but no
agent turns appear, it's the model, not the transport. Ops has a second API key ready.

### Speech recognition mangles the order ID repeatedly
**This is not a failure — it's the feature.** Let the confidence gate re-ask. Narrator: *"this
is exactly the case it's built for — it would rather ask again than guess."* Then have the
caller give the last four digits as scripted.

### Human agent can't join the channel
Fall back to the console-only handoff: the operator approves from the console without joining
the audio. The case file and context preservation still demo. Narrator explains that the audio
join is the interpreter path, and offer to show it after.

### Network drops entirely
Switch to the backup recording. Say plainly: *"we've lost the network, this is the recording of
the same flow, and we're happy to run it live again for you afterwards."* Judges respect this.
**Do not pretend a recording is live** — "unsafe AI behaviour" and dishonesty in a demo are how
teams lose credibility permanently.

### The room is very loud
Lean into it. This is the noise-resilience requirement demonstrating itself under conditions
you didn't control. Say so.

---

## Backup assets

Keep all of these on a local drive, not in the cloud:

- Full-run screen recording with audio (the same script, one take)
- Short 90-second version
- Static screenshots of the panel at the three key moments — policy block, escalation packet,
  idempotency block
- Architecture diagram as a standalone image
- A copy of the audit log JSON from a successful run

---

## Reset procedure between runs

Judges may ask for a second run. This must take under 60 seconds:

```bash
make demo-reset     # restores demo data to clean state, clears session store
```

Verify `ORD-4471` shows `refund_status: null` before starting again.

---

## Online evaluation specifics (5–6 Sep)

- **No mentoring, updates or modifications are permitted during this window.** Whatever is
  submitted on 4 Sep is what gets evaluated.
- Panel assesses **functionality, innovation, technical implementation, and use of Agora
  technologies**. Address all four explicitly.
- Have [05-judge-qa.md](05-judge-qa.md) open on a second screen.
- If asked about something you haven't built — say so plainly and say what you'd do. Bluffing
  is transparently worse than a clean "not yet, here's the plan."

## Finale specifics (12 Sep)

- Shark Tank format: problem, approach, technical implementation, **Agora implementation**,
  impact, future vision. Then live demo, then jury Q&A.
- The core solution **must remain unchanged** from the submission. UX polish, presentation
  quality, demo flow and storytelling may be improved — nothing else.
- Incorporate mentor feedback into the *pitch*, not the code.
- Lead with the demo if the format allows. The demo is stronger than the slides.
