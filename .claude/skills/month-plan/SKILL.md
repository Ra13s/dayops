---
name: month-plan
description: Monthly ceremony overhead analysis — shows meeting cost per project vs allocation, flags overcommitment, suggests standup frequency
argument-hint: [year month]
allowed-tools: Bash Read
---

# Monthly Ceremony Overhead Analysis

Analyzes the full month's calendar against project allocations.

If $ARGUMENTS contains year and month (e.g., "2026 4"), use those. Otherwise use current month.

## Prerequisites
- `user/profile.yaml` must exist
- Outlook must be running

## Process

### 1. Gather Data

Run: `python scripts/month_analysis.py $ARGUMENTS`
Parse the JSON output.

### 2. Present Per-Project Breakdown

For each project with an allocation:

```
### [Project] ([X]% = [Y]h allocated)
Meeting hours: [Z]h | Ceremony overhead: [N]% | Work hours left: [W]h

By type:
  [daily] Xh | [sync] Xh | [retro] Xh | ...

Recurring meetings:
  Meeting Name — Nx @ Xm = Xh/month
  Meeting Name — Nx @ Xm = Xh/month
```

### 3. Flag Issues

- Projects with overhead > 40%: "Warning: [X]% of your [Project] time is ceremonies"
- Projects with negative work hours: "Critical: Meeting hours exceed allocation — you need to cut meetings"

### 4. Recommendations

For each flagged project:
- Calculate standup cost as % of allocation
- Suggest attendance frequency based on allocation %
- Show sensitivity: "If you skip [meeting] 3x/week, you gain [X]h"
- Suggest specific days to attend based on the allocation table

### 5. Summary

```
### Monthly Summary
Total meeting hours: [X]h / [Y]h ([Z]%)
Actual work hours: [W]h
```
