# ADR-005: Playwright Token Capture Over Entra App Registration

**Status:** Accepted (with Entra app as fallback)
**Date:** 2026-04-13
**Context:** Need access to Teams chats, To Do tasks, and Tempo worklogs. Two approaches available: (A) register an Azure Entra app with OAuth, or (B) capture auth tokens from the browser via Playwright.

## Decision

Use **Playwright token capture** as the primary integration method. Keep Entra app as a documented alternative for users who need stability or whose IT policy blocks browser automation.

## Reasoning

### What Playwright gives us (zero setup)

| Service | API | Token audience | Read | Write |
|---------|-----|---------------|------|-------|
| Teams chats | `teams.cloud.microsoft/api/chatsvc/` | `ic3.teams.office.com` | Yes | — |
| Microsoft To Do | `substrate.office.com/todob2/api/v1/` | `outlook.office.com` | Yes | Yes |
| Tempo worklogs | `app.tempo.io/rest/tempo-timesheets/4/` | Tempo JWT | Yes | Yes |

**All proven working** — we created and deleted To Do tasks, created and deleted Tempo worklogs, and read 297 Teams messages in a single day.

### Why not Entra app first?

| Concern | Playwright | Entra App |
|---------|------------|-----------|
| Setup time | 0 min | 15-30 min in Azure portal |
| Admin consent | None | Needed for Chat.Read, ChannelMessage.Read.All |
| IT approval | None | May be blocked by corporate policy |
| Token management | Auto-refresh by navigating to web app | Refresh tokens, longer-lived |
| API stability | Internal APIs, could change | Graph API, stable and versioned |
| External chats | Not in conversation list API | Works with Chat.Read scope |

**The killer advantage:** Zero admin consent. In many organizations, getting an Entra app approved takes days or weeks. With Playwright, the agent works on day one.

### Limitations we accept

1. **Token expiry (~1h):** Re-capture by navigating to the web app. The agent does this automatically.
2. **Internal APIs:** Microsoft could change `chatsvc` or `substrate` endpoints without notice. If they do, we fall back to Entra app.
3. **Playwright browser must be running:** Adds resource overhead. Browser dies when Claude Code closes.
4. **External/federated chats not in conversation list:** The Teams internal API doesn't return cross-tenant chats. Messages ARE in the DOM when the chat is open, but can't be programmatically discovered.
5. **Security optics:** Capturing tokens from network requests looks like credential theft, even though it's your own session.

### When to use Entra app instead
- IT policy explicitly blocks browser automation
- External chat coverage is critical (Graph API with Chat.Read covers these)
- Stability matters more than setup speed (production deployment)
- Multiple users sharing the same app registration

## Alternatives Considered
- **Entra app only:** Clean, stable, official. But admin consent blocks adoption and adds days of setup.
- **Softeria MCP with Entra app:** Best of both — official Graph API, your own app. But still needs admin for Chat.Read.
- **Playwright only (chosen for MVP):** Works immediately, covers 90% of use cases. Entra app documented as upgrade path.

## Consequences
- New users can start using the agent immediately — no Azure portal, no admin
- Agent must handle token refresh gracefully (navigate → capture → retry)
- External chats are a known gap until Entra app is set up
- Setup guide documents both paths with clear comparison table
