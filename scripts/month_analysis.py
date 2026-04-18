"""Monthly ceremony overhead analysis.

Usage:
    python scripts/month_analysis.py                     # current month
    python scripts/month_analysis.py 2026 4              # specific month

Reads project config from user-profile.yaml.
Outputs JSON to stdout.
"""
import sys
import os
import calendar
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from collections import defaultdict
from scripts.utils import get_outlook, get_calendar_items, output_json

try:
    import yaml
except ImportError:
    print('Error: pip install pyyaml', file=sys.stderr)
    sys.exit(1)


def load_profile(path='user-profile.yaml'):
    if not os.path.exists(path):
        # Fall back to example
        example = 'user-profile.example.yaml'
        if os.path.exists(example):
            path = example
        else:
            print(f'Error: {path} not found. Copy user-profile.example.yaml and fill in your details.', file=sys.stderr)
            sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def classify_project(subject, organizer, profile):
    """Classify a meeting to a project using keywords, then organizer fallback."""
    s = subject.lower()

    # Keyword match (highest priority)
    for proj_name, proj_config in (profile.get('projects') or {}).items():
        keywords = proj_config.get('keywords', [])
        for kw in keywords:
            if kw.lower() in s:
                return proj_name

    # Organizer fallback
    for org_name, proj_name in (profile.get('organizer_projects') or {}).items():
        if org_name.lower() in organizer.lower():
            return proj_name

    # Admin detection
    admin_keywords = ['reminder', 'meeldetuletus', 'tunnid', 'raport']
    if any(k in s for k in admin_keywords):
        return 'Admin'

    return 'Unclassified'


def classify_meeting_type(subject):
    """Classify meeting type by keywords in subject."""
    s = subject.lower()
    if any(k in s for k in ['daily', 'dly', 'standup']): return 'daily'
    if 'retro' in s: return 'retro'
    if any(k in s for k in ['planning', 'planeerimine']): return 'planning'
    if 'refinement' in s: return 'refinement'
    if any(k in s for k in ['review', 'demo']): return 'review/demo'
    if any(k in s for k in ['sync', 'sünk', 'infovahetus']): return 'sync'
    if any(k in s for k in ['reminder', 'meeldetuletus']): return 'reminder'
    if '(optional)' in s: return 'optional'
    return 'meeting'


def is_room_booking(meeting, user_name, profile):
    """Detect room bookings to filter out."""
    subject = meeting['subject']
    organizer = meeting['organizer']
    is_self = user_name.lower() in organizer.lower()

    # Check configured patterns
    for pattern in profile.get('room_booking_patterns', []):
        if pattern.lower() in subject.lower():
            return True

    # Self-organized + short nonsensical name with no spaces
    if is_self and len(subject.strip()) < 15 and ' ' not in subject.strip():
        return True

    return False


def get_work_days_in_month(year, month, time_off_dates=None):
    """Count work days in a month, excluding weekends and time off."""
    time_off = set(time_off_dates or [])
    days = 0
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        dt = datetime(year, month, day)
        date_str = dt.strftime('%Y-%m-%d')
        if dt.weekday() < 5 and date_str not in time_off:
            days += 1
    return days


def main():
    args = sys.argv[1:]
    now = datetime.now()
    if len(args) >= 2:
        year, month = int(args[0]), int(args[1])
    else:
        year, month = now.year, now.month

    profile = load_profile()
    user_name = profile.get('name', '')
    ns = get_outlook()

    # Collect time-off dates
    time_off_dates = []
    for e in profile.get('time_off', []):
        d = e.get('date', '')
        if isinstance(d, str):
            time_off_dates.append(d)
        else:
            time_off_dates.append(d.strftime('%Y-%m-%d'))

    # Gather all meetings for the month
    all_meetings = []
    days_in_month = calendar.monthrange(year, month)[1]
    for day_num in range(1, days_in_month + 1):
        day = datetime(year, month, day_num)
        if day.weekday() >= 5:
            continue
        meetings = get_calendar_items(ns, day)
        for m in meetings:
            m['date'] = day.strftime('%Y-%m-%d')
            m['day_name'] = day.strftime('%A')
        all_meetings.extend(meetings)

    # Filter
    canceled = [m for m in all_meetings if m['is_canceled']]
    room_bookings = [m for m in all_meetings if not m['is_canceled'] and is_room_booking(m, user_name, profile)]
    real_meetings = [m for m in all_meetings if not m['is_canceled'] and not is_room_booking(m, user_name, profile)]

    # Classify and aggregate
    project_data = defaultdict(lambda: {
        'total_hours': 0,
        'by_type': defaultdict(float),
        'by_name': defaultdict(lambda: {'count': 0, 'duration_min': 0}),
    })

    for m in real_meetings:
        proj = classify_project(m['subject'], m['organizer'], profile)
        mtype = classify_meeting_type(m['subject'])
        hours = m['duration_min'] / 60

        pd = project_data[proj]
        pd['total_hours'] += hours
        pd['by_type'][mtype] += hours
        pd['by_name'][m['subject']]['count'] += 1
        pd['by_name'][m['subject']]['duration_min'] = m['duration_min']

    # Build output
    work_days = get_work_days_in_month(year, month, time_off_dates)
    work_hours = work_days * 8
    projects_output = []

    for proj_name in sorted(project_data.keys(), key=lambda p: -project_data[p]['total_hours']):
        pd = project_data[proj_name]
        proj_config = (profile.get('projects') or {}).get(proj_name, {})
        allocation_pct = proj_config.get('allocation')

        proj_out = {
            'name': proj_name,
            'meeting_hours': round(pd['total_hours'], 1),
            'allocation_pct': allocation_pct,
        }

        if allocation_pct and allocation_pct > 0:
            alloc_hours = work_hours * (allocation_pct / 100)
            proj_out['allocated_hours'] = round(alloc_hours, 1)
            proj_out['ceremony_overhead_pct'] = round((pd['total_hours'] / alloc_hours) * 100)
            proj_out['work_hours_remaining'] = round(alloc_hours - pd['total_hours'], 1)

        proj_out['by_type'] = {k: round(v, 1) for k, v in sorted(pd['by_type'].items(), key=lambda x: -x[1])}
        proj_out['recurring_meetings'] = [
            {
                'name': name,
                'count': info['count'],
                'duration_min': info['duration_min'],
                'total_hours': round((info['count'] * info['duration_min']) / 60, 1),
            }
            for name, info in sorted(pd['by_name'].items(), key=lambda x: -x[1]['count'])
        ]

        projects_output.append(proj_out)

    total_meeting_hours = sum(pd['total_hours'] for pd in project_data.values())

    output_json({
        'month': f'{year}-{month:02d}',
        'work_days': work_days,
        'work_hours': work_hours,
        'total_calendar_items': len(all_meetings),
        'canceled': len(canceled),
        'room_bookings': len(room_bookings),
        'real_meetings': len(real_meetings),
        'total_meeting_hours': round(total_meeting_hours, 1),
        'total_work_hours_remaining': round(work_hours - total_meeting_hours, 1),
        'meeting_pct_of_total': round((total_meeting_hours / work_hours) * 100) if work_hours else 0,
        'projects': projects_output,
    })


if __name__ == '__main__':
    main()
