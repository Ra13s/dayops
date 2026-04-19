---
name: onboard
description: Set up or update your Day Planner profile through an interactive interview. Creates user/profile.yaml.
allowed-tools: Bash Read Write Grep mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql mcp__claude_ai_Atlassian__searchAtlassian
---

# Onboarding Interview

Guide a new user through setting up their profile. The output is `user/profile.yaml`.

## Prerequisites Check

Before starting the interview, check and install prerequisites automatically:

### Step 0: Detect Platform & Language

**Platform detection (automatic):**
```bash
python -c "import sys; print(sys.platform)"
```
- `win32` → `platform: windows`
- `darwin` → `platform: mac`
- `linux` → `platform: linux`

Confirm with user: "Detected: [platform]. Is that correct?"

**Language preference:**
Ask: "What language should DayOps use for generated text? Original content (Teams, email, Jira) always stays as-is."
- Default: English (en)
- Common options: English (en), Estonian (et), German (de)
- Accept any language name or ISO code

### Step 0.5: Install & Verify Prerequisites

**Python packages (install automatically if missing):**
- All platforms: `pip install pyyaml 2>/dev/null`
- Windows only: `pip install pywin32 2>/dev/null`

Run this silently — don't bother the user unless it fails.

**Outlook (platform-dependent):**
- **Windows**: verify Outlook COM:
  ```python
  python -c "import win32com.client; o = win32com.client.Dispatch('Outlook.Application'); ns = o.GetNamespace('MAPI'); print(f'Outlook OK: {ns.GetDefaultFolder(6).Items.Count} emails')"
  ```
  If this fails: "Please open Outlook and try again."
- **Mac/Linux**: verify Playwright MCP is available (needed for Outlook Web token capture). If not, guide install:
  ```bash
  claude mcp add playwright -s user -- npx -y @anthropic-ai/mcp-playwright
  ```
  "On Mac/Linux, calendar and email are read via Outlook Web. Playwright MCP is required (not optional)."

**Atlassian MCP (recommended):**
- Check if Atlassian MCP tools are available
- If not connected: guide user through OAuth: "I need to connect to your Jira. Let me start the authentication..."
- If connected: pull a test query to confirm access and find the cloud ID

**Playwright MCP (required on Mac/Linux, recommended on Windows — enables Teams, To Do, Tempo, and on Mac/Linux: calendar + email):**
- Check if Playwright tools are available (e.g., `mcp__playwright__browser_navigate`)
- If not available, offer to install:
  "Playwright MCP enables Teams chat scanning, To Do tasks, and Tempo time logging. Install it now?"
  ```bash
  claude mcp add playwright -s user -- npx -y @anthropic-ai/mcp-playwright
  ```
  After install, restart Claude Code for the tools to appear.
- If available: "Playwright MCP ready — Teams, To Do, and Tempo integration enabled."

**GitLab MCP (optional):**
- Check if GitLab tools are available
- If not: note for later. Not blocking.

Report what's connected:
```
Data source check:
  ✓ Outlook COM — email + calendar
  ✓ Atlassian MCP — Jira (cloud ID: xxx)
  ✓ Playwright MCP — Teams chats + To Do + Tempo worklogs
  ✗ GitLab — not configured
  
Proceeding with all core sources. GitLab can be added later.
```

## Interview Flow

### Step 1: Personal Info
Ask:
- "What are your work hours?" (default: 10:00-18:00)
- "When do you usually have lunch?" (default: 12:00, 20min)
- "What's your daily meeting budget in hours?" (default: 2.5h)
- "Which country for public holidays?" (default: EE)

### Step 2: Projects
Ask: "What are your projects and approximate time allocation %?"

For each project, ask:
- Keywords that appear in meeting subjects for this project
- Jira cloud ID and project keys (if applicable)

### Step 3: Calendar Analysis
Pull the current month's calendar using:
```
python scripts/month_analysis.py
```

Present findings:
- List all unique meetings grouped by detected project
- Show unclassified meetings — ask user to classify them
- Identify room bookings — ask user to confirm
- Show case-insensitive duplicates — ask user to confirm

### Step 4: Organizer Mapping
For meetings that couldn't be classified by keywords, show organizer names.
Ask: "Which project does [organizer] belong to?"

### Step 5: Ceremony Overhead Analysis
For each project, calculate and present:
- Total meeting hours / month
- Allocated hours / month
- Ceremony overhead %
- Work hours remaining

Flag projects where overhead > 40%.

### Step 6: Standup Schedule
For each recurring daily/standup meeting:
- Show the cost: "[meeting] 5x/week = [X]h/month = [Y]% of your [project] allocation"
- Ask: "Which days do you want to attend?" or "Skip entirely?"
- On skip days, ask what reminder to show (e.g., "check async notes")

### Step 7: Conditional Meetings
For remaining recurring meetings, ask:
- "Do you always attend this, or only sometimes?"
- If sometimes: "What determines if you go?" (e.g., check Jira for tasks, check agenda)
- "How long does this meeting actually take?" (vs booked duration)
- "Do you need prep time?"

### Step 8: People
Ask: "Who are your key people per project? (name, role, expertise)"
These are used for delegation suggestions.

### Step 9: Expertise
Ask: "What are your expertise areas?"
Used to match implicit questions in group chats that the user should answer.

### Step 10: Noise Filters
Ask: "What email notifications are noise for you?"
Pre-populate with defaults (GitLab, Confluence digest, Jira).
Ask if any should be added or removed.

### Step 11: Discover Teams Conversations (if Playwright available)
Navigate Playwright to Teams web and discover external chat conversation IDs:

1. Navigate to `https://teams.microsoft.com`, wait for sidebar to load
2. Run `scripts/discover_teams_chats.js` via `browser_evaluate` (or the inline JS equivalent)
3. The script extracts all conversation IDs from the sidebar `data-tabster` attributes
4. External chats are identified by `trust-indicator` elements in the DOM
5. Present findings: "Found X chats: Y internal (API-accessible), Z external (cached IDs needed)"
6. Save external chat IDs to `user/profile.yaml` → `teams_conversations.external`

This only needs to run once. External conversation IDs are stable — they never change.
To refresh (new external contacts), re-run `/onboard` or manually add IDs.

### Step 12: Write Profile
Generate `user/profile.yaml` from all answers.
Show the user the file and ask for confirmation.

### Step 13: First Morning Briefing
Offer to run the morning briefing immediately:
"Profile saved. Want me to run your morning briefing now?"
If yes, run /morning.
