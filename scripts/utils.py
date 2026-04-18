"""Shared utilities for data gathering scripts.

Platform-aware: Outlook COM functions only import win32com when called (Windows).
HTTP functions work on any platform.
"""
import sys
import io
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# Fix encoding for non-ASCII characters on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# DayOps uses direct HTTPS calls with captured browser tokens.
# Ignore ambient proxy env vars here because this workspace may set
# dummy localhost proxies (for sandboxing) that break real API calls.
DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get_outlook():
    """Initialize and return Outlook COM namespace. Windows only."""
    import win32com.client
    outlook = win32com.client.Dispatch('Outlook.Application')
    return outlook.GetNamespace('MAPI')


def format_date_for_outlook(dt):
    """Format datetime for Outlook COM restriction filter.

    CRITICAL: Must use European DD/MM/YYYY format.
    US format MM/DD/YYYY causes Outlook to parse months as days.
    """
    return dt.strftime('%d/%m/%Y 12:00 AM')


def get_calendar_items(ns, day):
    """Get deduplicated calendar items for a single day.

    Returns list of dicts with: start, end, duration_min, subject, organizer,
    response, attendee_count, body_preview, is_canceled.

    Handles:
    - European date format for Outlook COM
    - GetFirst/GetNext iteration (IncludeRecurrences makes Count infinite)
    - Case-insensitive deduplication by subject + start time
    - Skips all-day events (Duration >= 1440)
    """
    cal = ns.GetDefaultFolder(9)
    items = cal.Items
    items.Sort('[Start]')
    items.IncludeRecurrences = True

    next_day = day + timedelta(days=1)
    restriction = (
        f"[Start] >= '{format_date_for_outlook(day)}' "
        f"AND [Start] < '{format_date_for_outlook(next_day)}'"
    )
    restricted = items.Restrict(restriction)

    seen = set()
    meetings = []
    item = restricted.GetFirst()
    while item:
        try:
            start_str = str(item.Start)[11:16]
            key = f'{item.Subject.lower()}_{start_str}'
            if key not in seen and item.Duration < 1440:
                seen.add(key)
                end_dt = item.Start + timedelta(minutes=item.Duration)
                resp_map = {
                    0: 'None', 1: 'Organizer', 2: 'Tentative',
                    3: 'Accepted', 4: 'Declined', 5: 'Not responded'
                }
                required = item.RequiredAttendees or ''
                attendee_count = len([a for a in required.split(';') if a.strip()])
                body = (item.Body[:500] if item.Body else '').strip()

                meetings.append({
                    'start': start_str,
                    'end': str(end_dt)[11:16],
                    'duration_min': item.Duration,
                    'subject': tag_untrusted(item.Subject, 'calendar'),
                    'organizer': item.Organizer if hasattr(item, 'Organizer') else '',
                    'response': resp_map.get(item.ResponseStatus, 'Unknown'),
                    'attendee_count': attendee_count,
                    'body_preview': tag_untrusted(body[:300], 'calendar'),
                    'is_canceled': 'Canceled' in item.Subject or 'Cancelled' in item.Subject,
                })
            item = restricted.GetNext()
        except Exception:
            item = restricted.GetNext()

    meetings.sort(key=lambda m: m['start'])
    return meetings


def merge_time_ranges(meetings):
    """Merge overlapping meeting time ranges to get wall-clock occupied time.

    Returns total occupied minutes (not sum of durations).
    Parallel meetings count once.
    """
    if not meetings:
        return 0

    def to_minutes(time_str):
        h, m = map(int, time_str.split(':'))
        return h * 60 + m

    ranges = sorted(
        [(to_minutes(m['start']), to_minutes(m['end'])) for m in meetings]
    )

    merged = [ranges[0]]
    for start, end in ranges[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    return sum(end - start for start, end in merged)


def api_get(url, token, timezone=None):
    """GET request with Bearer token. Returns parsed JSON.

    If timezone is provided (e.g., "Europe/Tallinn"), the Outlook API
    returns times in that timezone instead of UTC.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if timezone:
        headers["Prefer"] = f'outlook.timezone="{timezone}"'
    req = urllib.request.Request(url, headers=headers)
    try:
        with DIRECT_OPENER.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode('utf-8', errors='replace')[:200]}


def strip_html(html):
    """Strip HTML tags and decode common entities."""
    if not html:
        return ''
    text = re.sub(r'<[^>]+>', '', html)
    for entity, char in [('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'),
                         ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'")]:
        text = text.replace(entity, char)
    return text.strip()


def tag_untrusted(text, source):
    """Wrap user-generated text in untrusted XML tags for prompt injection defense.

    Escapes closing tag sequences to prevent breakout attacks.
    Source must be a hardcoded literal (a-z and underscore only).
    """
    if not text:
        return text
    assert re.match(r'^[a-z_]+$', source), f"source must be [a-z_]+ literal, got: {source}"
    safe_text = text.replace('</untrusted>', '</ untrusted>')
    safe_text = safe_text.replace('<untrusted', '< untrusted')
    return f'<untrusted source="{source}">{safe_text}</untrusted>'


def output_json(data):
    """Print data as JSON to stdout for LLM consumption."""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
