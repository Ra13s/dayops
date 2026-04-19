# ADR-002: Delegation Decision Tree

**Status:** Accepted
**Date:** 2026-04-10
**Context:** Busy professionals receive 250-300 Teams messages/day, emails, Jira tickets, and ad-hoc requests. Need a systematic way to decide: do it, delegate it, or ignore it.

## Decision

Six-outcome decision tree applied to every incoming item:

```
INCOMING ITEM
  → Is this actually for me?        NO → IGNORE / REDIRECT
  → Is it urgent / blocking?        YES → DO IT NOW
  → Needs MY specific knowledge?    NO → Someone else can? → DELEGATE
  → Is it recurring?                YES → Can automate? → AUTOMATE
  → Otherwise                       → SCHEDULE in focus block
  → No one else, not urgent         → ADD TO TODO
```

## Reasoning

### Inspiration
- **Panda Planner delegation flowchart:** "Should I delegate this?" decision tree (time → recurring → automatable → skills → trainable)
- **Eisenhower Matrix:** Urgent/important quadrants, but too simple for a multi-project professional's reality
- **GTD (David Allen):** Capture → clarify → organize → reflect → engage. Our tree is the "clarify" step.
- **Jurgen Appelo (Management 3.0):** 7 levels of delegation — we simplified to 6 outcomes since the agent suggests, not the user.

### Why six outcomes instead of four (Eisenhower)
A multi-project professional has more options than "do" or "delegate":
1. **DO NOW** — urgent + needs my expertise (Blocker Jira, prod incident)
2. **SCHEDULE** — needs my brain but not urgent (architecture analysis, spec writing)
3. **DELEGATE** — someone else can handle it with context
4. **AUTOMATE** — recurring + templatable (status reports, onboarding steps)
5. **IGNORE/REDIRECT** — not my problem, point to right person
6. **ADD TO TODO** — only I can do it, not urgent, batch for later

Eisenhower misses AUTOMATE and IGNORE — both critical for high-message-volume professionals.

### The key gate: "Needs MY specific knowledge?"
This is where the agent earns its value. It uses the user's expertise profile to determine:
- Decisions in your area of expertise → probably needs you
- Review for a component you designed → probably needs you
- Bug in a component someone else owns → DELEGATE
- Question about a process another team handles → REDIRECT

The LLM reasons about this; rules can't cover every case.

### Priority order for morning queue
When multiple items pass through the tree as "DO NOW" or "SCHEDULE," sort by:
1. **Unblock others** — your 5min reply = their 8h wait
2. **Time-sensitive** — deadline today
3. **Quick decisions** — yes/no, approvals (2min, huge impact)
4. **Meeting prep** — don't go in blind
5. **Small TODOs** — clear the mental queue (< 15min rule)
6. **Jira reviews** — stay in the loop

This is based on **David Allen's 2-minute rule** (scaled to 15min for senior roles) and the principle that **unblocking others has the highest leverage**.

## Alternatives Considered
- **Pure LLM judgment:** No rules, let the LLM decide. Risk: inconsistent, sometimes delegates everything, sometimes nothing.
- **Pure rules engine:** Explicit rules for every case. Risk: too rigid, can't handle ambiguous cases (implicit questions in group chats).
- **Hybrid (chosen):** Rules for the obvious cases, LLM for the grey areas. The decision tree handles 80% mechanically; the LLM reasons about the remaining 20%.

## Consequences
- Every incoming item gets classified before being shown to the user
- User sees "DELEGATE to [person]" not just "here's a message"
- The delegation suggestions improve as the people list in the profile grows
