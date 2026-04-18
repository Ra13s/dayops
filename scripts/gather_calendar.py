"""Gather calendar data from Outlook for a date range.

Usage:
    python scripts/gather_calendar.py                              # today (COM)
    python scripts/gather_calendar.py 2026-04-10                   # specific day (COM)
    python scripts/gather_calendar.py --token TOKEN                # today (HTTP)
    python scripts/gather_calendar.py --token TOKEN 2026-04-10     # specific day (HTTP)

On Windows with Outlook desktop: no --token needed (uses COM).
On Mac/Linux: pass --token captured from Outlook Web via Playwright.

Outputs JSON to stdout.
"""
import sys
import os
import argparse
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPTS_DIR))

from datetime import datetime, timedelta
from scripts.utils import (
    get_outlook, get_calendar_items, merge_time_ranges, output_json,
    api_get, strip_html, tag_untrusted,
)


def load_profile(path='user-profile.yaml'):
    try:
        import yaml
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


def is_room_booking(subject, organizer, profile):
    """Detect self-booked placeholder room events that should not count as meetings."""
    user_name = (profile.get('name') or '').lower()
    subject_lower = subject.lower()
    organizer_lower = organizer.lower()

    for pattern in profile.get('room_booking_patterns', []):
        if pattern.lower() in subject_lower:
            return True

    return bool(user_name and user_name in organizer_lower and len(subject.strip()) < 15 and ' ' not in subject.strip())


def parse_date_args(args):
    """Parse positional date arguments."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if not args.dates:
        return today, today
    elif len(args.dates) == 1:
        return datetime.strptime(args.dates[0], '%Y-%m-%d'), datetime.strptime(args.dates[0], '%Y-%m-%d')
    else:
        return datetime.strptime(args.dates[0], '%Y-%m-%d'), datetime.strptime(args.dates[1], '%Y-%m-%d')


def detect_timezone():
    """Detect local IANA timezone name for Outlook API Prefer header.

    Priority: user-profile.yaml timezone > system detection > None (UTC fallback).
    """
    # 1. Try user-profile.yaml
    try:
        import yaml
        profile_path = os.path.join(os.path.dirname(SCRIPTS_DIR), 'user-profile.yaml')
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = yaml.safe_load(f)
            tz = profile.get('timezone')
            if tz:
                return tz
    except Exception:
        pass

    # 2. System detection
    try:
        import time
        # Windows timezone abbreviations to IANA mapping
        win_tz_map = {
            'FLE': 'Europe/Tallinn', 'EET': 'Europe/Tallinn', 'EEST': 'Europe/Tallinn',
            'CET': 'Europe/Berlin', 'CEST': 'Europe/Berlin', 'W. Europe': 'Europe/Berlin',
            'GTB': 'Europe/Bucharest', 'E. Europe': 'Europe/Bucharest',
            'Romance': 'Europe/Paris', 'GMT': 'Europe/London', 'BST': 'Europe/London',
            'Eastern': 'America/New_York', 'Central': 'America/Chicago',
            'Mountain': 'America/Denver', 'Pacific': 'America/Los_Angeles',
            'AUS Eastern': 'Australia/Sydney', 'Tokyo': 'Asia/Tokyo',
            'India': 'Asia/Kolkata', 'China': 'Asia/Shanghai',
        }
        tzname = time.tzname[1] if time.daylight else time.tzname[0]
        for key, iana in win_tz_map.items():
            if key in tzname:
                return iana

        # Mac/Linux: try /etc/timezone or /etc/localtime
        if os.path.exists('/etc/timezone'):
            with open('/etc/timezone') as f:
                tz = f.read().strip()
                if '/' in tz:
                    return tz
        if os.path.islink('/etc/localtime'):
            link = os.readlink('/etc/localtime')
            # e.g. /usr/share/zoneinfo/Europe/Tallinn
            if 'zoneinfo/' in link:
                return link.split('zoneinfo/')[-1]

        # Last resort: Python tzinfo
        local_tz = str(datetime.now().astimezone().tzinfo)
        if '/' in local_tz:
            return local_tz
    except Exception:
        pass
    return None


def get_calendar_items_http(token, day, profile=None):
    """Fetch calendar items for a single day via Outlook REST API.

    Returns same structure as COM-based get_calendar_items().
    """
    profile = profile or {}
    tz = detect_timezone()
    start_dt = day.strftime('%Y-%m-%dT00:00:00')
    end_dt = (day + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00')
    url = (
        f"https://outlook.office.com/api/v2.0/me/calendarview"
        f"?startDateTime={start_dt}&endDateTime={end_dt}"
        f"&$top=100&$orderby=Start/DateTime"
        f"&$select=Subject,Start,End,Organizer,ResponseStatus,Attendees,Body,IsCancelled,IsAllDay"
    )
    data = api_get(url, token, timezone=tz)
    if 'error' in data:
        return []

    resp_map = {
        'none': 'None', 'organizer': 'Organizer', 'tentativelyAccepted': 'Tentative',
        'accepted': 'Accepted', 'declined': 'Declined', 'notResponded': 'Not responded',
    }

    seen = set()
    meetings = []
    for item in data.get('value', []):
        if item.get('IsAllDay', False):
            continue

        start_str = item['Start']['DateTime'][11:16]
        end_str = item['End']['DateTime'][11:16]
        subject = item.get('Subject', '')

        # Duration in minutes
        start_full = datetime.strptime(item['Start']['DateTime'][:19], '%Y-%m-%dT%H:%M:%S')
        end_full = datetime.strptime(item['End']['DateTime'][:19], '%Y-%m-%dT%H:%M:%S')
        duration_min = int((end_full - start_full).total_seconds() / 60)

        if duration_min >= 1440:
            continue

        key = f'{subject.lower()}_{start_str}'
        if key in seen:
            continue
        seen.add(key)

        organizer = item.get('Organizer', {}).get('EmailAddress', {}).get('Name', '')
        response_raw = item.get('ResponseStatus', {}).get('Response', 'none')
        attendees = item.get('Attendees', [])
        # Count only required attendees to match COM behavior
        required_attendees = [a for a in attendees if a.get('Type') == 'Required']
        body_raw = item.get('Body', {}).get('Content', '')
        is_canceled = item.get('IsCancelled', False) or 'Canceled' in subject or 'Cancelled' in subject

        if is_room_booking(subject, organizer, profile):
            continue

        meetings.append({
            'start': start_str,
            'end': end_str,
            'duration_min': duration_min,
            'subject': tag_untrusted(subject, 'calendar'),
            'organizer': organizer,
            'response': resp_map.get(response_raw, 'Unknown'),
            'attendee_count': len(required_attendees),
            'body_preview': tag_untrusted(strip_html(body_raw)[:300], 'calendar'),
            'is_canceled': is_canceled,
        })

    meetings.sort(key=lambda m: m['start'])
    return meetings


def find_gaps(meetings, work_start='10:00', work_end='18:00', lunch_time='12:00', lunch_duration=20):
    """Find gaps between meetings within work hours.

    Returns list of gaps with: start, end, duration_min, classification.
    Classification: 'quick' (<30m), 'comms' (30-60m), 'focus' (60m+).
    """
    def to_minutes(time_str):
        h, m = map(int, time_str.split(':'))
        return h * 60 + m

    ws = to_minutes(work_start)
    we = to_minutes(work_end)
    lt = to_minutes(lunch_time)

    # Build occupied ranges from non-canceled meetings
    occupied = sorted(
        [(to_minutes(m['start']), to_minutes(m['end']))
         for m in meetings if not m['is_canceled']]
    )

    # Merge overlapping
    merged = []
    for start, end in occupied:
        start = max(start, ws)
        end = min(end, we)
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Find gaps
    gaps = []
    prev_end = ws
    for start, end in merged:
        if start > prev_end:
            gap_dur = start - prev_end
            gap_start_str = f'{prev_end // 60:02d}:{prev_end % 60:02d}'
            gap_end_str = f'{start // 60:02d}:{start % 60:02d}'

            is_lunch = lt >= prev_end and lt < start

            if gap_dur < 30:
                classification = 'quick'
            elif gap_dur < 60:
                classification = 'comms'
            else:
                classification = 'focus'

            gaps.append({
                'start': gap_start_str,
                'end': gap_end_str,
                'duration_min': gap_dur,
                'classification': classification,
                'contains_lunch': is_lunch,
            })
        prev_end = end

    # Final gap to end of day
    if prev_end < we:
        gap_dur = we - prev_end
        gap_start_str = f'{prev_end // 60:02d}:{prev_end % 60:02d}'
        gap_end_str = f'{we // 60:02d}:{we % 60:02d}'

        if gap_dur < 30:
            classification = 'quick'
        elif gap_dur < 60:
            classification = 'comms'
        else:
            classification = 'focus'

        gaps.append({
            'start': gap_start_str,
            'end': gap_end_str,
            'duration_min': gap_dur,
            'classification': classification,
            'contains_lunch': lt >= prev_end and lt < we,
        })

    return gaps


def detect_conflicts(meetings):
    """Find overlapping meetings (parallel scheduling conflicts).

    Returns list of conflict pairs: [{meeting_a, meeting_b}].
    """
    def to_minutes(time_str):
        h, m = map(int, time_str.split(':'))
        return h * 60 + m

    active = [m for m in meetings if not m['is_canceled']]
    conflicts = []

    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            a_start = to_minutes(active[i]['start'])
            a_end = to_minutes(active[i]['end'])
            b_start = to_minutes(active[j]['start'])
            b_end = to_minutes(active[j]['end'])

            if a_start < b_end and b_start < a_end:
                conflicts.append({
                    'meeting_a': active[i]['subject'],
                    'meeting_b': active[j]['subject'],
                    'overlap_start': max(a_start, b_start),
                    'overlap_end': min(a_end, b_end),
                })

    return conflicts


def main():
    parser = argparse.ArgumentParser(description='Gather calendar data')
    parser.add_argument('dates', nargs='*', help='YYYY-MM-DD [end_date]')
    parser.add_argument('--token', help='Outlook REST API Bearer token (non-Windows)')
    args = parser.parse_args()

    start_date, end_date = parse_date_args(args)
    profile = load_profile()
    # Resolve token: "env" means read from DAYOPS_OUTLOOK_TOKEN env var
    token = args.token
    if token == 'env':
        token = os.environ.get('DAYOPS_OUTLOOK_TOKEN')
    use_http = token is not None

    if not use_http:
        ns = get_outlook()

    days = []
    day = start_date
    while day <= end_date:
        if day.weekday() < 5:
            if use_http:
                meetings = get_calendar_items_http(token, day, profile)
            else:
                meetings = get_calendar_items(ns, day)

            active_meetings = [m for m in meetings if not m['is_canceled']]
            occupied_min = merge_time_ranges(active_meetings)
            gaps = find_gaps(meetings)
            conflicts = detect_conflicts(meetings)

            days.append({
                'date': day.strftime('%Y-%m-%d'),
                'day_name': day.strftime('%A'),
                'meetings': meetings,
                'meeting_count': len(active_meetings),
                'occupied_minutes': occupied_min,
                'occupied_hours': round(occupied_min / 60, 1),
                'gaps': gaps,
                'focus_hours': round(sum(g['duration_min'] for g in gaps if g['classification'] == 'focus') / 60, 1),
                'conflicts': conflicts,
                'conflict_count': len(conflicts),
            })
        day += timedelta(days=1)

    output_json({
        'date_range': {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d'),
        },
        'days': days,
    })


if __name__ == '__main__':
    main()
