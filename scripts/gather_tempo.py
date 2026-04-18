"""Gather Tempo worklogs for a date range.

Usage:
    python scripts/gather_tempo.py --token JWT --from 2026-04-01 --to 2026-04-30
    python scripts/gather_tempo.py --token env --from 2026-04-01 --to 2026-04-30

Token can be captured via Playwright from the Jira Tempo page (audience
`Tempo-Bearer`). When --token is "env", reads from DAYOPS_TEMPO_TOKEN.

Reads `tempo.atlassian_account_id` from user-profile.yaml for worker filtering.

Returns JSON with:
- total_hours: sum of all worklogs in range
- by_origin_task: hours per numeric originTaskId (Jira internal issue ID)
- by_date: hours per YYYY-MM-DD
- worklogs: raw list with id, date, seconds, originTaskId, comment

originTaskId is a numeric Jira issue ID. The agent resolves these to Jira
project keys via Atlassian MCP (scripts can't call MCP). See
scripts/jira-id-cache.json for cached mappings.
"""
import sys
import os
import io
import json
import argparse
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.utils import DIRECT_OPENER  # utils.py handles stdout wrapping on Windows

TEMPO_SEARCH_URL = "https://app.tempo.io/rest/tempo-timesheets/4/worklogs/search"


def load_worker_id():
    """Read the Atlassian account ID from user-profile.yaml."""
    try:
        import yaml
        profile_path = 'user-profile.yaml'
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = yaml.safe_load(f)
            return profile.get('tempo', {}).get('atlassian_account_id')
    except Exception:
        pass
    return None


def fetch_worklogs(token, date_from, date_to, worker_id):
    """Call the Tempo search API for worklogs in [date_from, date_to]."""
    body = json.dumps({
        "from": date_from,
        "to": date_to,
        "workerId": [worker_id] if worker_id else [],
    }).encode('utf-8')
    headers = {
        "Authorization": f"Tempo-Bearer {token}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(TEMPO_SEARCH_URL, data=body, headers=headers, method='POST')
    try:
        with DIRECT_OPENER.open(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode('utf-8', errors='replace')[:300]}


def main():
    parser = argparse.ArgumentParser(description='Gather Tempo worklogs for a date range')
    parser.add_argument('--token', required=True, help='Tempo JWT or "env" to read DAYOPS_TEMPO_TOKEN')
    parser.add_argument('--from', dest='date_from', required=True, help='YYYY-MM-DD')
    parser.add_argument('--to', dest='date_to', required=True, help='YYYY-MM-DD')
    parser.add_argument('--worker', help='Atlassian account ID (default: from user-profile.yaml)')
    args = parser.parse_args()

    token = args.token
    if token == 'env':
        token = os.environ.get('DAYOPS_TEMPO_TOKEN')
    if not token:
        print(json.dumps({"error": "No Tempo token provided"}), file=sys.stderr)
        sys.exit(1)

    worker_id = args.worker or load_worker_id()
    if not worker_id:
        print(json.dumps({"error": "No worker ID — set tempo.atlassian_account_id in user-profile.yaml or pass --worker"}), file=sys.stderr)
        sys.exit(1)

    data = fetch_worklogs(token, args.date_from, args.date_to, worker_id)
    if isinstance(data, dict) and 'error' in data:
        print(json.dumps(data))
        sys.exit(1)

    by_origin_task = defaultdict(float)
    by_date = defaultdict(float)
    worklogs = []
    total_seconds = 0

    for w in data:
        seconds = w.get('timeSpentSeconds', 0)
        origin_task_id = w.get('originTaskId')
        started = w.get('started', '')
        date = started[:10]

        total_seconds += seconds
        by_origin_task[str(origin_task_id)] += seconds / 3600
        by_date[date] += seconds / 3600

        worklogs.append({
            'tempoWorklogId': w.get('tempoWorklogId'),
            'date': date,
            'hours': round(seconds / 3600, 2),
            'originTaskId': origin_task_id,
            'comment': w.get('comment', ''),
        })

    output = {
        'date_range': {'from': args.date_from, 'to': args.date_to},
        'worker_id': worker_id,
        'total_hours': round(total_seconds / 3600, 1),
        'worklog_count': len(worklogs),
        'by_origin_task': {k: round(v, 2) for k, v in by_origin_task.items()},
        'by_date': {k: round(v, 2) for k, v in sorted(by_date.items())},
        'worklogs': worklogs,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
