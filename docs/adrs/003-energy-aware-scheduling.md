# ADR-003: Energy-Aware Scheduling (No Fixed Daily Template)

**Status:** Accepted
**Date:** 2026-04-10
**Context:** Productivity advice typically prescribes "do deep work first thing in the morning." Some users report that mornings are warm-up time, not focus time. Need a scheduling approach that respects individual energy patterns AND adapts to daily calendar reality.

## Decision

1. **No fixed daily template** — every day is different. Read today's calendar, find gaps, assign work.
2. **Energy profile** determines what type of work fits each time period, configurable per user.
3. **Calendar-aware gap assignment** — gaps are classified by size AND energy phase.

## Reasoning

### Why not a fixed template?
A typical productivity template:
```
10:00-12:00  Focus block
12:00-12:30  Lunch
12:30-14:00  Focus block
14:00-16:00  Meetings
16:00-18:00  Wrap up
```

This fails on day one for anyone with multiple projects:
- Monday might have a sprint review at 10:00 and retro at 14:00
- Wednesday might be meeting-free until 13:00
- Thursday might have back-to-back meetings all morning

**The calendar IS the template.** The agent reads reality, not a prescription.

### Why energy phases?

**Chronobiology research:**
- Monk & Leng (1982), Lack & Wright (1993): Most people peak cognitively 2-4h after waking
- Daniel Pink ("When," 2018): Morning peak → afternoon dip → evening recovery
- **But 20-25% of the population are "evening types"** whose peak comes later

Example user self-reported pattern:
- Morning: warm-up phase (comms, quick tasks)
- Afternoon: peak focus (deep work)
- Transport: joins standups from phone → comms only

**We trust the user's self-knowledge over general research.** The energy profile is configurable:

```yaml
energy_profile:
  transport: "comms"      # phone only, no desk work
  morning: "warm-up"      # small TODOs, replies, unblocking
  afternoon: "peak"       # deep work, architecture
  late: "winding-down"    # meetings, reviews
  evening: "focus"        # optional, from home
```

### Gap classification: size + energy

| Gap size | Morning (warm-up) | Afternoon (peak) |
|----------|-------------------|------------------|
| < 30min | Quick tasks, replies | Quick tasks, replies |
| 30-60min | Comms catchup | Short focus task |
| 60min+ | **NOT deep work** — still warm-up tasks | **FOCUS BLOCK** — assign top Jira |

The key insight: **a 2-hour morning gap is NOT a focus block** for a warm-up-morning user. It's 2 hours of warm-up tasks. Only afternoon gaps get deep work assigned. For a peak-morning user, the opposite applies.

### Supporting research
- **Gerald Weinberg:** Adding projects reduces productive time (5 projects → 35% loss from switching)
- **Mark, Gonzalez, Harris (2005):** 23 minutes to fully resume deep work after interruption
- **Csikszentmihalyi (1990):** Flow state requires 15-25 min of uninterrupted work to enter → minimum useful focus block is ~45min
- **Perlow (1999):** "Quiet time" policies increased engineering productivity by 59%

### The 15-minute rule
From GTD, scaled for senior roles:
- Takes < 15min AND someone waiting → **do it now** (any energy phase)
- Takes < 15min AND nobody waiting → **batch into morning warm-up**
- Takes > 15min → **schedule in afternoon focus block**

## Alternatives Considered
- **Fixed template with override:** Set a default schedule, let the user adjust daily. Problem: the default is always wrong, and adjusting daily is the same work as calendar-aware scheduling.
- **Pure chronotype-based:** Assign focus based on circadian peak. Problem: the user's calendar doesn't care about their chronotype. A meeting at 14:00 ruins the focus block regardless of peak alertness.
- **No energy model, just gap size:** Treat all 60min+ gaps as focus blocks. Problem: assigns deep work to morning when the user can't focus, leading to frustration and abandoned plans.

## Consequences
- Agent never assigns deep work to morning gaps (for warm-up users)
- Agent checks energy profile before classifying gaps
- Plans feel natural and achievable, not prescriptive
- Early testers report feeling more productive because plans match their natural rhythm
