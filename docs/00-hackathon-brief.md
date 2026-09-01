# Hackathon brief — source of truth

Everything here is transcribed from the official Commudle event page. When in doubt,
this file wins over memory or assumption.

---

## Event

**EchoSphere: Agora Conversational AI Hackathon**, hosted by Knotic.
Hybrid format. Grand Finale offline in Delhi.
Total prize pool **$3,000**. 5 tracks / 5 problem statements.
Community partners: GDG Cloud New Delhi, GDG New Delhi, GDG Nagpur (~114k members combined).

Framing from the organisers:

> "This isn't another chatbot hackathon. Your challenge is to create voice-native AI
> experiences that can hold natural conversations, handle interruptions, remember context,
> call external tools, and take meaningful actions in real time."

## Timeline (2026)

| Round | Dates | Stage |
|---|---|---|
| 1 | 21 Jul – 25 Aug | Registration & team formation |
| 2 | 26 – 28 Aug | Idea submission & application screening |
| 3 | 29 Aug – 3 Sep | Online mentorship & development sprint |
| 4 | 4 – 7 Sep | Project submission, online evaluation, elimination |
| 5 | 12 Sep | Grand Finale & final judging |

Detail:

- **29 Aug – 3 Sep** — build. One dedicated 1:1 mentorship session per team. Agora Discord
  for technical support; WhatsApp group for product guidance and announcements.
- **4 Sep, 23:59 IST** — hard submission deadline. Mentorship ends.
- **5 – 6 Sep** — online demo to the evaluation panel. Assessed on **functionality,
  innovation, technical implementation, and use of Agora technologies**.
  **No mentoring, updates or modifications permitted during this window.**
- **7 Sep** — finalists announced.
- **8 – 11 Sep** — finale prep. Core solution must remain unchanged; UX, presentation
  quality, demo flow and storytelling may be improved.
- **12 Sep** — offline Grand Finale. Shark Tank–style pitch: problem, approach, technical
  implementation, **Agora implementation**, impact, future vision. Live demo + jury Q&A.

## Mandatory technology

> "Every project must use **Agora Conversational AI as the primary real-time voice
> interaction layer**. Projects that only use speech-to-text and text-to-speech around a
> chatbot without real-time conversational capabilities will not qualify."

Any LLM, ASR, TTS, vector DB, cloud platform or external API is permitted —
OpenAI, Gemini, Claude, DeepSeek, ElevenLabs and others are explicitly allowed.
**Agora must remain the core voice interaction platform.**

## Every project must demonstrate

1. Real-time voice interaction
2. Natural conversation
3. User interruption handling
4. Contextual memory
5. External tool or API integration
6. At least one meaningful action
7. Human escalation where appropriate

## Required submission artefacts

- Working prototype
- Source code repository
- README
- Architecture diagram
- 3–5 minute demo video
- Live demo during evaluation
- List of technologies used
- Known limitations

## Disqualifiers — read these twice

- Agora is **not central** to the solution
- The project is **only a voice-enabled chatbot**
- The demo is **entirely prerecorded**
- **Unsafe AI behaviour** is demonstrated
- The project is **copied without significant modification**

## Team rules

- Team size **2–4 members** (the overview's "4+" is wrong; the FAQ caps it at 4)
- Open to students, professionals, researchers, startups, independent developers
- No registration fee
- Certificates for eligible participants; special recognition for finalists and winners

## Own problem statements

> "**No.** Teams are expected to build their solution based on one of the official problem
> statements announced for the hackathon."

The overview page mentions an "Open Innovation track" — **the FAQ contradicts this and the
FAQ is more specific.** Treat Open Innovation as unavailable. Worth confirming with
organisers if you ever want to rely on it.

---

## PS5 — verbatim (our problem statement)

> Build a real-time multilingual voice AI agent for a customer assistance, public
> information or non-clinical support line.
>
> The caller may be stressed, speaking from a noisy environment, using more than one
> language or unable to clearly explain the issue.
>
> The agent should calmly collect essential information, confirm its understanding and
> transfer the caller to a human when confidence is low or the situation requires human
> judgement.

### The solution should demonstrate

1. Multilingual and code-switched voice interaction
2. Natural interruption handling
3. Information collection through conversation
4. Repetition and confirmation of critical details
5. Low-confidence detection
6. Prioritized question flow
7. Background-noise resilience
8. Human escalation with context preservation
9. Integration with ticketing or case-management systems
10. Clear boundaries around what the AI is allowed to do

### Example scenario

> A caller begins in Hindi, switches to English and provides incomplete details while
> people are speaking in the background. The AI should collect and confirm the minimum
> required information and transfer the case to a human with a concise conversation summary.

### Safety restrictions — the prototype must NOT

- Provide medical diagnosis
- Replace trained emergency responders
- Provide legal, financial or emergency instructions as authoritative advice
- Present uncertain AI-generated information as confirmed fact

---

## The other four problem statements (for reference)

- **PS1** — Adaptive voice interview platform with multiple AI interviewer roles
- **PS2** — Real-time voice AI sales agent doing qualification and objection handling
- **PS3** — Voice AI co-teacher in a live digital classroom
- **PS4** — Real-time AI incident commander joining a live incident room

See [01-decision-log.md](01-decision-log.md) for why we chose PS5 over these.
