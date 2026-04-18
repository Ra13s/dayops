# Day Planner Agent — Setup Guide

## Prerequisites

- Windows with Outlook desktop app installed and running
- Python 3.10+ with `pywin32` and `pyyaml` installed
- Claude Code (VS Code extension or CLI)
- Node.js 18+ (for MCP servers)
- Playwright MCP (for Tempo worklog tracking via browser auth)

```bash
pip install pywin32 pyyaml
```

### Playwright MCP

Required for Tempo worklogs, Teams chats, and To Do tasks via browser session capture. This is the **zero-admin-consent** path — no Entra app registration needed.

```bash
claude mcp add playwright -s user -- npx -y @anthropic-ai/mcp-playwright
```

This starts a Chromium browser that Playwright controls. On first use:
1. The agent navigates to Teams/Jira/To Do web
2. Microsoft SSO logs you in automatically (if you've logged in once in that browser)
3. The agent captures auth tokens from network requests
4. Uses those tokens to call APIs directly

**What Playwright unlocks (no Entra app needed):**

| Service | Read | Write | API used |
|---------|------|-------|----------|
| **Tempo worklogs** | Yes | Yes | `app.tempo.io/rest/tempo-timesheets/4/` |
| **Teams chats** | Yes | — | `teams.cloud.microsoft/api/chatsvc/` |
| **Microsoft To Do** | Yes | Yes | `substrate.office.com/todob2/api/v1/` |

**Limitations:**
- Playwright browser must be running (agent starts it automatically)
- Tokens expire (~1h) — agent re-captures by navigating to the web app again
- Uses internal Microsoft APIs (not Graph API) — could change without notice
- Browser session dies when Claude Code closes — next session needs SSO again (usually instant)
- First-time setup: log into Microsoft account once in the Playwright browser

### Login Prerequisite and Fail-Fast Rule

For DayOps morning briefing, authenticated Playwright sessions are a hard prerequisite for:
- Outlook Web token capture
- Teams token capture
- Microsoft To Do token capture

If the agent opens Playwright and lands on:
- a Microsoft sign-in page
- an account picker
- a public app landing page such as "Welcome to To Do"

then the agent should stop and wait for the user to log in, instead of continuing with partial or degraded data collection.

Why this matters:
- unauthenticated runs produce missing or misleading data
- token extraction fails in confusing ways when the browser is not logged in
- ingesting the wrong mailbox scope or fallback data increases prompt-injection surface unnecessarily

Recommended behavior:
1. Open Outlook / Teams / To Do in Playwright
2. Confirm the app is actually authenticated
3. Only then capture network requests and extract tokens
4. If not authenticated, ask the user to log in and retry after confirmation

## 1. Atlassian MCP (Jira + Confluence)

This is a built-in Claude Code integration. No local install needed.

### Setup
1. In Claude Code, the Atlassian MCP should be available by default
2. If not connected, run the authenticate tool — it will give you an OAuth URL
3. Sign in with your Atlassian account
4. After auth, test with: "Search Jira for my open issues"

### Finding Your Cloud ID
You need your Jira Cloud ID for the user profile. Run this in Claude Code:
```
Use the Atlassian MCP to search for "my issues"
```
The cloud ID appears in the API responses (UUID format like `524d863a-af3b-4a71-8c0b-42bada4c756b`).

Add to `user-profile.yaml`:
```yaml
projects:
  MyProject:
    jira_cloud_id: "your-cloud-id-here"
    jira_projects: ["PROJ"]
```

---

## 2. Microsoft 365 — Two Integration Paths

### Choose your path:

| | **Option A: Playwright** (zero setup) | **Option B: Entra App + Softeria MCP** (proper) |
|---|---|---|
| **Setup time** | 0 min (just open Teams/To Do once) | 15-30 min (Azure portal + npm) |
| **Admin consent** | None needed | Needed for Chat.Read + ChannelMessage.Read.All |
| **Teams chats** | Read via internal API | Read via Graph API |
| **To Do** | Read + write via internal API | Read + write via Graph API |
| **Tempo** | Read + write (only option) | Not covered (still need Playwright) |
| **Stability** | Internal APIs may change | Official Graph API, stable |
| **Token lifetime** | ~1h, auto-recapture | Refresh token, long-lived |
| **Works offline** | No (browser needed) | Yes (cached token) |

**Recommendation:** Start with **Option A (Playwright)** — works immediately, no setup, no admin. Move to **Option B** later if you want stability or if internal APIs break.

Both options can coexist — Playwright for Tempo (always needed), Softeria for Teams/To Do if you want Graph API stability.

### Option A: Playwright (Zero Setup)

Already configured if you followed the Playwright MCP setup above. The agent:
1. Opens Teams web / To Do web / Jira Tempo in the Playwright browser
2. Your Microsoft SSO session authenticates automatically
3. Agent captures auth tokens from network requests
4. Calls the internal APIs directly with those tokens

**APIs used:**

| Service | Endpoint | Token audience |
|---------|----------|---------------|
| Teams chats | `teams.cloud.microsoft/api/chatsvc/emea/v1/users/ME/conversations` | `ic3.teams.office.com` |
| To Do lists | `substrate.office.com/todob2/api/v1/taskfolders` | `outlook.office.com` |
| To Do create | `substrate.office.com/todob2/api/v1/taskfolders/{id}/tasks` (POST) | `outlook.office.com` |
| Tempo worklogs | `app.tempo.io/rest/tempo-timesheets/4/worklogs` | Tempo JWT |

**First-time setup:** Open Teams web (`teams.microsoft.com`) in the Playwright browser and log in with your Microsoft account. SSO will persist for future sessions.

Operational note: if SSO did not persist and Playwright shows sign-in or a public landing page, do not continue the briefing until the user logs in again in that Playwright browser context.

No Entra app, no admin consent, no npm packages. Just Playwright + your existing Microsoft session.

---

### Option B: Entra App + Softeria MCP (Official Graph API)

Uses the Softeria MCP server (`@softeria/ms-365-mcp-server`) as the MCP wrapper, but authenticated through **your own** Azure Entra app — your tokens stay local, no third-party access.

Uses the Softeria MCP server (`@softeria/ms-365-mcp-server`) as the MCP wrapper, but authenticated through **your own** Azure Entra app — your tokens stay local, no third-party access.

### What you get

| Capability | Tool | Read | Write |
|---|---|---|---|
| **To Do tasks** | `list-todo-tasks`, `create-todo-task` | Yes | Yes (without `--read-only`) |
| **Teams chats** | `list-chats`, `list-chat-messages`, `send-chat-message` | Yes | Yes (without `--read-only`) |
| **Calendar** | `list-calendar-events`, `get-calendar-view` | Yes | Yes (without `--read-only`) |
| **Email** | `list-mail-messages`, `get-mail-message` | Yes | Yes (without `--read-only`) |

### Step 1: Register Your Azure Entra App

1. Go to [Microsoft Entra admin center → App registrations](https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Click **New registration**
3. Name: `Day Planner Agent`
4. Supported account types: **"Accounts in this organizational directory only"** (the first option, Single tenant)
5. Leave Redirect URI blank for now — we'll add it in the next step
6. Click **Register**
7. You're now on the app's **Overview** page. Copy these two values (both shown here):
   - **Application (client) ID**
   - **Directory (tenant) ID**

### Step 1b: Configure Platform & Redirect URI

1. In your app's left sidebar, click **Authentication**
2. Under **Platform configurations**, click **Add a platform**
3. Select the **Mobile and desktop applications** tile
4. Check the suggested URI: `https://login.microsoftonline.com/common/oauth2/nativeclient`
5. Click **Configure**
6. Scroll down to **Advanced settings**
7. Set **Allow public client flows** to **Yes** (required for device code flow)
8. Click **Save** at the top

### Step 2: Add API Permissions

1. In your app's left sidebar, click **API permissions**
2. Click **Add a permission** → **Microsoft Graph** → **Delegated permissions**
3. Search for and add each of these:

| Permission | What it gives you | Admin consent? |
|---|---|---|
| `User.Read` | Basic profile (required for sign-in) | No |
| `offline_access` | Stay logged in (refresh token, no re-login every hour) | No |
| `Tasks.ReadWrite` | Read + create To Do tasks | No |
| `Chat.Read` | Read Teams 1:1 and group chat messages | **Maybe** — depends on tenant policy |
| `ChannelMessage.Read.All` | Read Teams channel messages (e.g., #general) | **Yes** — admin required |
| `Calendars.Read` | Read calendar events | No |
| `Mail.Read` | Read email | No |

4. After adding all permissions, check the **Status** column:
   - `Chat.Read` and `ChannelMessage.Read.All` likely show "Not granted for [your org]" — an admin must click **"Grant admin consent for [your org]"** on this page
   - All other permissions: you consent yourself during first login
   - If admin won't grant Teams permissions, the agent still works for To Do, calendar, and email

**Tip:** Run `npx -y @softeria/ms-365-mcp-server --list-permissions --org-mode` to verify the exact scopes the MCP server needs for the current version.

**Do NOT add:** `Mail.Send`, `Chat.ReadWrite` (agent should not send email or Teams messages)

If `Chat.Read` is blocked by your admin, the agent still works — you just won't get Teams message scanning. Everything else (To Do, calendar, email) works without admin.

### Alternative: Automated Setup via Azure CLI

Instead of the manual portal steps above, you can create everything with two commands. Requires `az login` first.

**Bash / Git Bash:**
```bash
# Create the app
APP=$(az ad app create \
  --display-name "Day Planner Agent" \
  --sign-in-audience AzureADMyOrg \
  --public-client-redirect-uris "https://login.microsoftonline.com/common/oauth2/nativeclient" \
  --query "{appId:appId, id:id}" -o json)

APP_ID=$(echo $APP | jq -r .appId)
OBJ_ID=$(echo $APP | jq -r .id)

# Add all permissions + enable device code flow
az rest --method PATCH \
  --uri "https://graph.microsoft.com/v1.0/applications/$OBJ_ID" \
  --headers "Content-Type=application/json" \
  --body '{
    "isFallbackPublicClient": true,
    "requiredResourceAccess": [{
      "resourceAppId": "00000003-0000-0000-c000-000000000002",
      "resourceAccess": [
        {"id": "e1fe6dd8-ba31-4d61-89e7-88639da4683d", "type": "Scope"},
        {"id": "7427e0e9-2fba-42fe-b0c0-848c9e6a8182", "type": "Scope"},
        {"id": "2219042f-cab5-40cc-b0d2-16b1540b4c5f", "type": "Scope"},
        {"id": "f501c180-9344-439a-bca0-6cbf209fd270", "type": "Scope"},
        {"id": "767156cb-16ae-4d10-8f8b-41634cbf7a64", "type": "Scope"},
        {"id": "465a38f9-76ea-45b9-9f34-9e8b0d4b0b42", "type": "Scope"},
        {"id": "570282fd-fa5c-430d-a7fd-fc8dc98a9dca", "type": "Scope"}
      ]
    }]
  }'

echo "Client ID: $APP_ID"
echo "Tenant ID: $(az account show --query tenantId -o tsv)"
```

**PowerShell:**
```powershell
$APP = az ad app create `
  --display-name "Day Planner Agent" `
  --sign-in-audience AzureADMyOrg `
  --public-client-redirect-uris "https://login.microsoftonline.com/common/oauth2/nativeclient" `
  --query "{appId:appId, id:id}" -o json | ConvertFrom-Json

$APP_ID = $APP.appId
$OBJ_ID = $APP.id

az rest --method PATCH `
  --uri "https://graph.microsoft.com/v1.0/applications/$OBJ_ID" `
  --headers "Content-Type=application/json" `
  --body '{\"isFallbackPublicClient\":true,\"requiredResourceAccess\":[{\"resourceAppId\":\"00000003-0000-0000-c000-000000000002\",\"resourceAccess\":[{\"id\":\"e1fe6dd8-ba31-4d61-89e7-88639da4683d\",\"type\":\"Scope\"},{\"id\":\"7427e0e9-2fba-42fe-b0c0-848c9e6a8182\",\"type\":\"Scope\"},{\"id\":\"2219042f-cab5-40cc-b0d2-16b1540b4c5f\",\"type\":\"Scope\"},{\"id\":\"f501c180-9344-439a-bca0-6cbf209fd270\",\"type\":\"Scope\"},{\"id\":\"767156cb-16ae-4d10-8f8b-41634cbf7a64\",\"type\":\"Scope\"},{\"id\":\"465a38f9-76ea-45b9-9f34-9e8b0d4b0b42\",\"type\":\"Scope\"},{\"id\":\"570282fd-fa5c-430d-a7fd-fc8dc98a9dca\",\"type\":\"Scope\"}]}]}'

Write-Host "Client ID: $APP_ID"
Write-Host "Tenant ID: $(az account show --query tenantId -o tsv)"
```

**Permission GUIDs reference:**

| Permission | GUID |
|---|---|
| User.Read | `e1fe6dd8-ba31-4d61-89e7-88639da4683d` |
| offline_access | `7427e0e9-2fba-42fe-b0c0-848c9e6a8182` |
| Tasks.ReadWrite | `2219042f-cab5-40cc-b0d2-16b1540b4c5f` |
| Chat.Read | `f501c180-9344-439a-bca0-6cbf209fd270` |
| ChannelMessage.Read.All | `767156cb-16ae-4d10-8f8b-41634cbf7a64` |
| Calendars.Read | `465a38f9-76ea-45b9-9f34-9e8b0d4b0b42` |
| Mail.Read | `570282fd-fa5c-430d-a7fd-fc8dc98a9dca` |

**Note:** You still need an admin to grant consent for `Chat.Read` + `ChannelMessage.Read.All` in the Entra portal after creation.

### Step 3: Install Softeria MCP with Your App

```bash
claude mcp add ms365 -s user -e MS365_MCP_CLIENT_ID=YOUR_CLIENT_ID -e MS365_MCP_TENANT_ID=YOUR_TENANT_ID -- cmd /c "npx -y @softeria/ms-365-mcp-server --org-mode"
```

Replace `YOUR_CLIENT_ID` and `YOUR_TENANT_ID` with the actual values you copied in Step 1 (e.g., `08ad6f98-a4f8-4635-bb8d-f1a3044760f0`).

Flags:
- `--org-mode`: enables Teams access (required for chat messages)
- No `--read-only` — we need write access for creating To Do tasks
- The Entra app scopes are the real security boundary, not the MCP flag

### Step 4: Login

**Important:** You must pass your app credentials when logging in, otherwise it authenticates against Softeria's default app instead of yours.

On Windows (cmd/PowerShell):
```cmd
set MS365_MCP_CLIENT_ID=YOUR_CLIENT_ID && set MS365_MCP_TENANT_ID=YOUR_TENANT_ID && npx -y @softeria/ms-365-mcp-server --login
```

On bash/Git Bash:
```bash
MS365_MCP_CLIENT_ID=YOUR_CLIENT_ID MS365_MCP_TENANT_ID=YOUR_TENANT_ID npx -y @softeria/ms-365-mcp-server --login
```

This triggers a device code flow. Open the URL shown, enter the code, sign in with your Microsoft work account. Tokens are stored locally on your machine.

### Step 6: Verify

Restart Claude Code. Test:
- "List my To Do tasks" → should show your Microsoft To Do lists
- "List my recent Teams chats" → should show chat threads
- "What's on my calendar today?" → should show today's events

### Troubleshooting

**"Admin approval required"**: Your IT admin needs to consent to `Chat.Read` for your tenant. Ask them to approve your app (not Softeria's — it's your own app registration).

**"Invalid redirect URI"**: Make sure the redirect URI in Entra is under "Mobile and desktop applications", not "Single-page application" or "Web".

**"No Teams data"**: Make sure you used `--org-mode` flag. Without it, Teams and SharePoint tools are not exposed.

---

## 3. GitLab MCP

For merge requests, pipelines, and code review tracking.

### If Using GitLab.com or Self-Hosted GitLab

1. Generate a Personal Access Token:
   - GitLab → Settings → Access Tokens
   - Scopes: `read_api`, `read_user`, `read_repository`

2. Add to Claude Code MCP settings. In your Claude Code settings (`.claude/settings.json`):
```json
{
  "mcpServers": {
    "gitlab": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-gitlab"],
      "env": {
        "GITLAB_PERSONAL_ACCESS_TOKEN": "your-token-here",
        "GITLAB_API_URL": "https://gitlab.com/api/v4"
      }
    }
  }
}
```

Replace `GITLAB_API_URL` with your self-hosted URL if applicable.

---

## 4. Tempo Timesheets (Worklog Tracking)

Reads your logged hours from Tempo to track actual time spent per project vs allocation.

### How It Works

No Tempo API key needed. The agent uses Playwright to piggyback on your existing Jira session:

1. Playwright opens the Tempo timesheet page in Jira (you're already authenticated)
2. Captures the `Tempo-Bearer` JWT token from the browser's network requests
3. Calls the Tempo REST API directly with that token
4. Resolves Jira issue IDs to project names via Atlassian MCP

### Prerequisites

- Playwright MCP must be configured in Claude Code
- You must be logged into Jira in your browser
- Tempo must be installed in your Jira instance

### API Details

**Endpoint:** `POST https://app.tempo.io/rest/tempo-timesheets/4/worklogs/search`

**Auth:** `Authorization: Tempo-Bearer <jwt>` (captured from browser network)

**Request body:**
```json
{
  "from": "2026-04-01",
  "to": "2026-04-30",
  "workerId": ["your-atlassian-account-id"]
}
```

**Response:** Array of worklog entries with:
- `timeSpentSeconds` — duration
- `started` — date
- `originTaskId` — Jira internal issue ID (resolve via Atlassian MCP to get project key)
- `comment` — work description

**Token lifecycle:** JWT expires after ~15 minutes. The agent captures it once at morning briefing time. If it expires mid-session, re-navigate to Tempo page to get a fresh one.

### What You Get

The agent uses this data to:
- Track actual hours logged per project this month
- Compare against allocation targets
- Alert when falling behind or ahead: "Project Alpha is at 52h (target: 44h) — shift focus to Project Beta"
- Show monthly progress in morning briefings

---

## 5. Outlook COM (Local, No Setup Needed)

Already works if:
- You're on Windows
- Outlook desktop app is installed and running
- Python has `pywin32` installed

No tokens, no OAuth, no admin approval. The scripts talk directly to your running Outlook instance.

**Limitation:** Cannot access Microsoft To Do tasks created after 2025 (deprecated COM store). Use Graph API for To Do.

---

## MCP Configuration Summary

After setup, your Claude Code should have these MCP servers:

| MCP / Integration | Purpose | Required? |
|-------------------|---------|-----------|
| Atlassian | Jira tickets, Confluence, resolve Tempo task IDs | Yes |
| ms365 (Softeria + your Entra app) | To Do, Teams, Calendar, Email | Recommended |
| Playwright | Capture Tempo JWT for worklog tracking | Recommended |
| GitLab | MRs, pipelines | Optional |
| Outlook COM (no MCP) | Email, Calendar (local, Windows only) | Built-in fallback |

Verify in Claude Code:
```
List all available MCP tools
```

---

## Quick Start

1. Install prerequisites: `pip install pywin32 pyyaml`
2. Copy `user-profile.example.yaml` → `user-profile.yaml`
3. Open Claude Code in the `time-manager` directory
4. The agent will detect no profile and start the onboarding interview
5. Or run `/onboard` to set up manually

The onboarding interview will guide you through everything — you don't need to fill in the YAML manually.
