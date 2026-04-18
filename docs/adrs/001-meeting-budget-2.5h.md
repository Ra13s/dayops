# ADR-001: Daily Meeting Budget of 2.5 Hours

**Status:** Accepted
**Date:** 2026-04-10
**Context:** Professionals juggling multiple projects spend disproportionate time in meetings. Need a threshold to trigger "you should decline something."

## Decision

Default daily meeting budget: **2.5 hours**.

## Reasoning

### Research
- **Microsoft WorkLab (2021):** EEG data shows stress (beta wave activity) increases significantly after ~2h of consecutive video meetings. After 4 back-to-back meetings, ability to focus drops dramatically.
- **Luong & Rogelberg (2005):** Meeting fatigue is nonlinear — each additional hour costs more than the previous one.
- **Cal Newport (Deep Work):** Knowledge workers can sustain max ~4h of deep work per day. In an 8h day with lunch, 2.5h meetings leaves ~4.5h for actual work — right at the sustainable limit.

### Real-World Validation
Testing with a user managing 5+ projects showed:
- Naive (attend everything): **4.9h/day** meetings → 61% of time → near-zero deep work
- Optimized (with skip rules): **2.9h/day** → 37% → 4h deep work available
- 2.5h target is slightly aspirational vs the 2.9h optimized actual — pushes toward better behavior

### Budget Scenarios (8h work day)

| Budget | Meetings % | Deep work available |
|--------|-----------|---------------------|
| 2.0h | 25% | 5.0h — aggressive, only achievable on light days |
| **2.5h** | **31%** | **4.5h — sweet spot** |
| 3.0h | 38% | 4.0h — realistic but deep work starts to suffer |
| 3.5h | 44% | 3.5h — too permissive |

### Important nuance
**Distribution matters more than total.** 2.5h spread across the day with breaks is fine. 2.5h back-to-back is damaging. The agent should flag consecutive meeting blocks > 90min, not just total.

## Alternatives Considered
- **2.0h:** Too aggressive for multi-project roles — would mean declining mandatory ceremonies
- **3.0h:** Doesn't trigger the "should I skip this?" question often enough
- **No budget, just track:** Without a threshold, there's no signal to act on

## Consequences
- Agent flags days over 2.5h and suggests meetings to skip
- Optional meetings are first to be suggested for skipping
- Budget is configurable per user in `user-profile.yaml`
