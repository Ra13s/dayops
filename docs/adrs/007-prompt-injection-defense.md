# ADR 007: Prompt Injection Defense

## Status

Accepted

## Context

DayOps reads untrusted external content (Teams messages, emails, Jira descriptions, calendar bodies) and feeds it to Claude for analysis. This creates a prompt injection attack surface — an attacker could embed instructions in a Teams message or email body that Claude might follow.

Security researchers describe a "lethal trifecta" for AI agents — when an agent simultaneously:
1. Processes untrusted input
2. Has access to private data
3. Can change state or communicate externally

DayOps satisfies all three. Research from leading AI labs shows that published prompt injection defenses consistently fail against adaptive attackers. There is no silver bullet — defense must be layered.

## Decision

We implement defense-in-depth with three layers:

### Layer 1: Content Tagging (technical)

All gather scripts wrap user-generated text fields in `<untrusted source="...">` XML tags. Claude is specifically trained to respect XML boundary markers. System-generated metadata (timestamps, statuses) remains untagged.

**Critical:** The `tag_untrusted()` function escapes closing tag sequences (`</untrusted>` → `</ untrusted>`) to prevent breakout attacks where an attacker closes the tag early and injects instructions. The source attribute only accepts hardcoded `[a-z_]+` literals.

Content is truncated before tagging, so tags are always well-formed.

### Layer 2: Prompt Instructions (LLM-level)

Skills include explicit security instructions stating that `<untrusted>` content is data to summarize, never instructions to follow. Jira content from MCP (which cannot be script-tagged) is covered by the same instructions.

This layer also enforces:
- Write actions require explicit user confirmation
- Write-capable tokens should only be captured at moment of confirmed action
- Suspicious content should be flagged to the user

**Honest limitation:** This layer is a prompt instruction, not an architectural constraint. The agent has technical capability to capture write tokens and execute actions. The instruction reduces attack surface but does not eliminate it.

### Layer 3: Read-Only Briefing Pattern (design-level)

The morning briefing is designed as a read-only operation — it gathers and summarizes data without taking actions. Write operations (Tempo logging, To Do creation) are separate user-initiated flows. This limits the blast radius of a successful injection during the briefing.

## What We Chose Not To Do

- **Regex-based input filtering**: Trivially bypassed with encoding, typos, or rephrasing. False sense of security.
- **Dual-LLM content scanning**: Adds latency, cost, and per research is still not reliable against adaptive attackers.
- **Content sanitization/stripping**: Would lose legitimate information.
- **Multi-turn accumulation defense**: Injected content summarized into plan files could re-activate when read next day. Acknowledged but not solved — would require tagging to persist through summarization.

## Consequences

- All gather scripts produce tagged output — skills handle tags transparently
- Jira content requires skill-level instruction (no script-level tagging for MCP data)
- `tag_untrusted()` escapes content, adding ~5% to JSON payload size
- Write operations require extra user confirmation step (already mostly true, now codified)
- Defense is not foolproof — layered approach reduces but does not eliminate risk

## References

- [Anthropic: Mitigating prompt injection risk](https://www.anthropic.com/research/prompt-injection-defenses)
- [OWASP LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [Simon Willison: The Lethal Trifecta for AI Agents](https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents)
- [OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
