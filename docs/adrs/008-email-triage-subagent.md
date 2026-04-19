# ADR 008: Email Triage Subagent (Dual-LLM Defense)

## Status

Accepted

## Context

Email is DayOps' highest-risk untrusted content source. Anyone with the user's email address can inject text into the main agent's context. [ADR 007](007-prompt-injection-defense.md) covers general defenses (content tagging, security instructions, read-only briefing), but all three layers rely on the main agent respecting boundaries. Research from Anthropic, OpenAI, and DeepMind shows instruction-based defenses fail against adaptive attackers.

The **dual-LLM pattern** (also called the "CaMeL" pattern or "sandbox agent" pattern) is one of the few architectural defenses that holds up. A privileged agent with write capabilities delegates untrusted-content processing to a separate, locked-down agent. Even if injection succeeds against the sandboxed agent, it cannot escape that context to reach the agent with real tools.

## Decision

Dispatch a separate triage subagent to process raw email content before the main agent reads it.

### Architecture — File-based handoff

```
gather_email.py ──redirect──→ user/raw/email-raw.json
                                      │
                                      │ (main agent never reads this file)
                                      │
                              email-triager subagent
                                      │
                                      │ Reads file, triages
                                      ▼
                              Returns sanitized JSON
                                      │
                                      ▼
                              Main agent uses triaged JSON for briefing
```

The main agent writes the file via shell redirect (`> file`) but never reads it. Only the subagent's context sees raw email content.

Claude Code uses `.claude/agents/email-triager.md` directly:
- `model: haiku` — cheap, fast (~3-5s)
- `tools: [Read]` — only enough to read the one file passed in its prompt. No Bash, Write, Edit, or MCP.
- Strict JSON output schema
- Explicit instructions to never follow email content as directives
- Explicit instructions to read only the path given in its prompt

Codex uses the same file as the instruction source rather than a native Claude agent manifest:
- Spawn a subagent explicitly
- Read `.claude/agents/email-triager.md` as trusted repo instructions
- Pass only trusted user context plus the absolute path to `user/raw/email-raw.json`
- Do not paste raw email into the spawned prompt
- Treat the returned JSON as untrusted until the main agent validates it

### Why file-based handoff (not prompt-based)

The obvious approach — main agent runs `gather_email.py`, captures stdout, passes to subagent via prompt — fails. The captured stdout passes through the main agent's context before reaching the subagent. Any injection embedded in the email JSON would be visible to the main agent (which has write tools) before the subagent ever saw it. That defeats the dual-LLM boundary.

By redirecting stdout to a file the main agent never opens, the raw content exists only on disk and in the subagent's context. The main agent stays clean.

### Why This Works

For Codex, the main architectural guarantee is the quarantined file handoff: raw email never enters the main agent context. Codex should spawn a subagent, load `.claude/agents/email-triager.md` as trusted instructions, and pass only the absolute file path plus trusted user context. The returned JSON must be validated before use.

Instruction-based defenses can be overridden by cleverer instructions. This defense is architectural — the subagent literally cannot take write actions because the write tools are not available to it. Injection succeeds at most in making the subagent output bad JSON or wrong summaries. It cannot make the subagent create a Tempo worklog or send a Teams message.

### Scope

Email only. Teams and Jira are internal-organization sources with lower attacker access. Calendar body is low-volume and the calendar gather script already applies heavy structure.

The subagent triages all four arrays from gather_email.py: `emails`, `meeting_invites`, `meeting_cancellations`, `jira_summaries`. A single boundary simplifies reasoning.

## Consequences

- **Latency**: +3-5s per morning briefing for the Haiku triage call
- **Cost**: One Haiku call per briefing — negligible (~2K input + 1K output tokens)
- **Main agent never sees raw email body**. User asking "what did Regina say exactly?" must re-run gather_email or open Outlook.
- **Schema discipline**: Subagent returns strict JSON. Main agent validates before use; falls back gracefully on malformed output.
- **Defense strength**: Injection inside email content cannot reach the main agent's write tools, regardless of how cleverly it is crafted.

## What We Chose Not To Do

- **Triage Teams messages** — lower risk (internal org only, rate-limited channels). Revisit if Teams ever hosts external content at volume.
- **Triage Jira content** — same reasoning, plus Jira content arrives via MCP, not gather scripts. Would require a separate triage pipeline.
- **Give the subagent Read access beyond the one scratch file** — the subagent's Read tool is restricted by instruction to the exact path in its prompt. User-profile content is passed in the prompt text, not read by the subagent.
- **Persist triaged output** — transient per briefing. If the user wants raw email later, they open Outlook.

## Codex Adaptation

For Codex sessions, the repo instructions must explicitly tell the main agent to:
- never open `user/raw/email-raw.json`
- read `.claude/agents/email-triager.md` as the triager instruction source
- call `spawn_agent` for the triage step
- pass only trusted user context and the absolute raw file path to the spawned agent
- validate the returned JSON and skip the email section on failure

This preserves the file-based handoff and dual-agent separation. It does not claim stronger isolation than the active Codex sandbox and approval policy provide.

## References

- [ADR 007: Prompt Injection Defense](007-prompt-injection-defense.md) — foundational defenses that this ADR builds on
- [Simon Willison: Dual LLM pattern](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/)
- [The Attacker Moves Second](https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents) — research showing instruction-based defenses fail
