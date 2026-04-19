# ADR-004: Standup Attendance Based on Project Allocation

**Status:** Accepted
**Date:** 2026-04-10
**Context:** Professionals attending daily standups for multiple projects can lose disproportionate time to ceremonies. A 30min daily standup for a 15% project consumes 44% of the project's allocated time alone.

## Decision

Match recurring standup/daily meeting attendance frequency to project allocation percentage.

| Project allocation | Standup frequency | Rationale |
|---|---|---|
| 50%+ | Daily | Core project, need full context |
| 15-30% | 2-3x/week | Stay in loop, keep 80%+ for real work |
| 5-15% | 1x/week | Weekly context is enough |
| <5% | Async only | Read standup notes, skip meetings |

## Reasoning

### The math that triggered this decision

**Example: a 15% project with 26.4h/month allocation**

| If attend | Standup cost | % of allocation | Work time left |
|-----------|-------------|----------------|----------------|
| 5x/week (daily) | 9.2h | **44%** | 14.2h |
| 3x/week | 5.5h | 22% | 19.7h |
| **2x/week** | **3.7h** | **17%** | **20.8h** |
| 1x/week | 1.8h | 9% | 23.0h |

At daily attendance, **44% of the project's time goes to standups.** With other recurring meetings (refinement, retro, weekly sync), total ceremony overhead can reach **93%** — leaving almost no time for actual work.

After applying the 2x/week rule, meeting load drops significantly, leaving 5-6h of real work time.

### Session-based project work
Small-allocation projects (< 30%) shouldn't have daily presence. Instead of spreading 36 min/day across every day, **batch into focused sessions:**

- **15% project:** Pick one focus day per week. Full afternoon focus block. Other days: only quick chat replies (< 10min).
- **10% flex project:** As-needed. Some weeks zero, some weeks a full day.
- **< 5% project:** Reactive only. Attend meetings, nothing else.

### Example standup decisions

Users configure per-meeting rules:
- **Fixed schedule:** "Attend Tue + Thu only. Skip Mon/Wed/Fri. On skip days: check async notes."
- **Always attend:** "Done during transport (phone), doubles as time logging trigger. No desk time consumed."
- **Random/optional:** "~1.5x/week, skip when over meeting budget."
- **Conditional (Jira-based):** "Attend only if I have tasks in 'Ready for refinement' status." Agent checks Jira before the meeting.
- **Conditional (agenda-based):** "Attend only if agenda contains topics needing my input." Often runs 20min actual vs 60min booked.

## Alternatives Considered
- **Attend everything:** The default. Leads to 93% ceremony overhead on small projects and zero productive time.
- **Skip everything for small projects:** Loses context entirely. Missing one sprint's context creates catch-up debt.
- **Async-only for all:** Not realistic in organizations that rely on synchronous standups for coordination.

## Consequences
- Agent knows which days to show each standup as ATTEND vs SKIP
- Agent shows reminder on skip days: "Check async notes for [meeting]"
- Monthly ceremony analysis tracks whether attendance rules are being followed
- Can be recalibrated as project allocations change
