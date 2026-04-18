/**
 * Discover all Teams conversation IDs from the sidebar DOM.
 *
 * Run via Playwright: mcp__playwright__browser_evaluate with this script.
 * Returns JSON with all conversation IDs, names, and whether they're external.
 *
 * Usage (from Claude Code via Playwright):
 *   1. Navigate to teams.microsoft.com
 *   2. Wait for sidebar to load
 *   3. Run this script via browser_evaluate
 */
(() => {
  const tree = document.querySelector('[role="tree"]');
  if (!tree) return JSON.stringify({ error: 'No chat tree found. Is Teams loaded?' });

  const items = tree.querySelectorAll('[role="treeitem"][aria-level="2"]');
  const chats = [];

  for (const item of items) {
    const name = item.innerText?.split('\n')[0]?.trim();
    if (!name || name.length < 2) continue;

    // Extract conversation ID from data-tabster attribute
    const tabster = item.getAttribute('data-tabster');
    if (!tabster) continue;

    const match = tabster.match(/"names":\["([^"]+)"/);
    if (!match) continue;
    const convId = match[1];

    // Skip non-conversation items
    if (!convId.startsWith('19:')) continue;

    // Determine chat type
    let type = 'unknown';
    if (convId.includes('@thread.v2')) type = 'group';
    else if (convId.includes('@thread.tacv2')) type = 'channel';
    else if (convId.includes('@thread.skype')) type = 'skype';
    else if (convId.includes('meeting_')) type = 'meeting';
    else if (convId.includes('@unq.gbl.spaces')) type = 'oneOnOne';

    // Detect external chats by trust-indicator element
    const trustIndicator = item.querySelector('[id*="trust-indicator"]');
    const isExternal = trustIndicator !== null;

    // Detect which section (pinned/fast vs regular chats)
    const section = item.closest('[role="treeitem"][aria-level="1"]');
    const sectionName = section?.innerText?.split('\n')[0]?.trim() || 'unknown';

    chats.push({
      name,
      id: convId,
      type,
      external: isExternal,
      section: sectionName
    });
  }

  return JSON.stringify({
    total: chats.length,
    external: chats.filter(c => c.external).length,
    internal: chats.filter(c => !c.external).length,
    chats
  });
})()
