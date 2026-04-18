"""Extract a Bearer token from a Playwright network requests dump file.

Usage:
    python scripts/extract_token.py <requests_file> <url_pattern>

Examples:
    python scripts/extract_token.py .playwright-mcp/requests.txt outlook.office.com
    python scripts/extract_token.py .playwright-mcp/requests.txt ic3.teams.office.com
    python scripts/extract_token.py .playwright-mcp/requests.txt tempo

Reads the Playwright MCP network requests dump, finds the first request
whose URL matches the pattern, extracts the Bearer token from its
authorization header, and prints ONLY the token to stdout.

Exit code 0 on success, 1 if no matching token found.
"""
import sys
import re


def score_block(url_pattern, first_line, block):
    """Prefer request blocks that carry the most useful bearer for each service."""
    line = first_line.lower()
    score = 0

    # Outlook dumps often include both notification-channel callback tokens and
    # the actual OWA app token. The OWA token appears on startupdata/service
    # calls and works for calendar/email/todo APIs; the callback token does not.
    if 'outlook.office.com' in url_pattern.lower() or 'outlook.cloud.microsoft' in url_pattern.lower():
        if 'startupdata.ashx' in line:
            score += 100
        if 'service.svc' in line or 'published/service.svc' in line:
            score += 80
        if '/api/v2.0/' in line:
            score += 70
        if 'notificationchannel/' in line:
            score -= 100
        if 'embeddedusertokentype' in block.lower():
            score -= 20

    # For Teams, prefer the actual chatsvc token over broader mt/api tokens.
    if 'chatsvc' in url_pattern.lower() or 'teams.office.com' in url_pattern.lower():
        if '/api/chatsvc/' in line:
            score += 100
        if '/api/mt/' in line:
            score -= 20

    return score


def extract_token(filepath, url_pattern):
    """Extract Bearer token from Playwright network dump file.

    Returns the token string, or None if not found.
    """
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    blocks = re.split(r'\n(?=\[(?:GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\] )', content)

    candidates = []
    for idx, block in enumerate(blocks):
        first_line = block.split('\n')[0]
        if url_pattern.lower() not in first_line.lower():
            continue

        match = re.search(r'authorization:\s*Bearer\s+(eyJ[A-Za-z0-9_\-\.]+)', block)
        if match:
            candidates.append((score_block(url_pattern, first_line, block), idx, match.group(1)))
            continue

        match = re.search(r'authorization:\s*Tempo-Bearer\s+([A-Za-z0-9_\-\.]+)', block)
        if match:
            candidates.append((score_block(url_pattern, first_line, block), idx, match.group(1)))

    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]

    return None


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python scripts/extract_token.py <requests_file> <url_pattern>", file=sys.stderr)
        sys.exit(1)
    token = extract_token(sys.argv[1], sys.argv[2])
    if token:
        print(token)
        sys.exit(0)
    else:
        print(f"No token found for pattern '{sys.argv[2]}'", file=sys.stderr)
        sys.exit(1)
