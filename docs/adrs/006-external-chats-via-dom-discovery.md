# ADR-006: External/Federated Teams Chats via DOM Sidebar Discovery

**Status:** Accepted
**Date:** 2026-04-14
**Context:** Teams internal chat API (`chatsvc`) does not return external/federated conversations in the conversation list. Microsoft has confirmed this is by design (GitHub issue #12259). Users who communicate with people in other organizations see these chats in the Teams UI but cannot access them programmatically via any documented or undocumented API list endpoint.

## Decision

Use a two-step approach:
1. **DOM sidebar scraping** to discover external conversation IDs
2. **Standard chat API** to read messages using those IDs

## The Problem

| API | Lists external chats? | Reads external messages (if ID known)? |
|-----|----------------------|---------------------------------------|
| `chatsvc /users/ME/conversations` (IC3 token) | **No** | **Yes** |
| Microsoft Graph `/me/chats` | **No** (404 for federated) | **Yes** |
| Purview eDiscovery | **Not supported** | — |
| Teams sidebar DOM | **Yes** | N/A (DOM, not API) |

The gap is purely **discovery** — once you have the conversation ID, all APIs can read the messages fine.

## The Solution

### Step 1: Extract conversation IDs from sidebar DOM

The Teams web client stores conversation IDs in the `data-tabster` attribute of chat list items:

```javascript
// Each sidebar chat item has this pattern:
item.getAttribute('data-tabster')
// Returns: {"observed":{"names":["19:UUID_UUID@unq.gbl.spaces"]}}
```

External chats use the **same `@unq.gbl.spaces` format** as internal chats — not `@fed.unq.gbl.spaces` as some documentation suggests.

External chats can also be identified by a `trust-indicator` child element in the DOM:
```
id="trust-indicator:19:UUID_UUID@unq.gbl.spaces"
```

### Step 2: Read messages via standard API

With the extracted conversation ID, the standard `chatsvc` messages endpoint works:
```
GET /api/chatsvc/emea/v1/users/ME/conversations/{id}/messages
```

This returns full message history including sender, content, timestamps, and mentions — identical to internal chats.

## What We Tried (and What Failed)

| Approach | Result |
|----------|--------|
| `chatsvc` conversation list with various parameters | External chats never appear |
| Graph API `/me/chats` with `Chat.Read` scope | 404 for federated conversations |
| `externalsearchv3` endpoint for user MRI | Requires worker-internal auth, can't call from outside |
| Constructing `@fed.unq.gbl.spaces` IDs | External chats actually use regular `@unq.gbl.spaces` |
| Intercepting Web Worker fetch/XHR | Worker doesn't use fetch/XHR — uses WebSocket/postMessage |
| CDP network interception on worker | Can't intercept worker network at CDP level |
| Graph API token from Teams web (secondary audience) | Missing `Chat.Read` scope |
| DOM message reading (`data-tid="message"` selector) | **Works** for reading messages, but not for discovery |
| **DOM sidebar `data-tabster` attribute** | **Works** for ID discovery |
| **API with discovered ID** | **Works** for reading messages |

## Implementation

The `gather_teams.py` script gains a `--discover` mode:

1. Playwright navigates to Teams web
2. Scrape sidebar: extract all conversation IDs from `data-tabster` attributes
3. Identify external chats by presence of `trust-indicator` element
4. For each discovered ID, call the messages API
5. Return combined results (internal via list API + external via discovered IDs)

For hourly polling, the sidebar scrape only needs to happen once per session. The conversation IDs are stable — they don't change.

## Why This Works

Microsoft's limitation is intentional: the conversation *list* endpoint doesn't enumerate federated conversations. But the conversation *messages* endpoint has no such restriction — if you provide a valid ID, it returns messages regardless of federation status.

The Teams web client knows about these conversations (it shows them in the sidebar) because it loads them through a Web Worker using WebSocket/postMessage, bypassing the standard `chatsvc` REST API. The conversation IDs end up in the DOM as attributes for the UI framework (Fluent UI tree items).

## Alternatives Considered

- **Entra app with Graph API `Chat.Read`**: Same limitation — `/me/chats` doesn't list federated chats. Would only help if we had the ID already.
- **DOM-only approach (read messages from DOM)**: Works but slow (~5s per chat) and can't filter by time. The hybrid approach (DOM for IDs, API for messages) is faster and supports time-range queries.
- **Configure external contacts manually**: Simpler but requires the user to maintain a list and doesn't auto-discover new external chats.
- **Unified Audit Log**: Admin-only access, requires `Search-UnifiedAuditLog` PowerShell cmdlet. Not practical for a user-level tool.

## Consequences

- External chats are fully supported without any Entra app or admin consent
- Sidebar scrape adds ~2-3 seconds to the first poll of a session
- Conversation IDs can be cached after initial discovery
- New external contacts will appear in the sidebar automatically as conversations are created
- The approach depends on Teams web UI structure (DOM attributes) which could change in UI updates
