"""Gather morning briefing data in one shot.

Usage (Windows - COM for calendar/email, token for teams/todo):
    python scripts/gather_all.py --outlook-requests FILE --teams-requests FILE [--date YYYY-MM-DD]
    python scripts/gather_all.py --teams-requests FILE [--date YYYY-MM-DD]

Usage (Mac/Linux - tokens for everything):
    python scripts/gather_all.py --outlook-requests FILE --teams-requests FILE [--date YYYY-MM-DD]

Auto-detects platform:
- Windows without --outlook-requests: uses COM for calendar/email, token for todo
- Windows with --outlook-requests: uses tokens for everything (HTTP mode)
- Mac/Linux: --outlook-requests is required (no COM available)

Security: tokens are passed to subprocesses via environment variables, not CLI args.

When --email-raw-out is provided, raw email JSON is quarantined to that file
instead of being returned in stdout. This keeps the fast path compatible with
ADR 008.
"""
import sys
import os
import io
import json
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess

# Guard stdout wrapping - only wrap if not already UTF-8
if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS = sys.platform == 'win32'

# Import extract_token from the standalone script to avoid duplication
sys.path.insert(0, SCRIPTS_DIR)
from extract_token import extract_token


def run_script(script_args, label, env):
    """Run a Python script and return parsed JSON output."""
    try:
        result = subprocess.run(
            [sys.executable] + script_args,
            capture_output=True,
            timeout=90,
            env=env,
        )
        if result.returncode != 0:
            return label, {"error": result.stderr.decode('utf-8', errors='replace')[:500]}
        return label, json.loads(result.stdout.decode('utf-8', errors='replace'))
    except subprocess.TimeoutExpired:
        return label, {"error": "timeout (90s)"}
    except json.JSONDecodeError as e:
        return label, {"error": f"JSON parse error: {str(e)[:100]}"}
    except Exception as e:
        return label, {"error": str(e)[:200]}


def resolve_request_file(path_str):
    """Resolve a Playwright network dump file from common locations."""
    if not path_str:
        return None

    candidate = Path(path_str)
    if candidate.exists():
        return str(candidate.resolve())

    search_roots = [
        Path.cwd(),
        Path.cwd() / '.playwright-mcp',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Microsoft VS Code',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Microsoft VS Code' / '.playwright-mcp',
    ]

    for root in search_roots:
        if not str(root):
            continue
        try:
            direct = root / path_str
            if direct.exists():
                return str(direct.resolve())
            by_name = root / candidate.name
            if by_name.exists():
                return str(by_name.resolve())
        except OSError:
            continue

    return None


def run_email_to_file(script_args, outfile, env):
    """Run the email gatherer and quarantine raw output to a file."""
    try:
        out_path = Path(outfile)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable] + script_args,
            capture_output=True,
            timeout=90,
            env=env,
        )
        if result.returncode != 0:
            return {
                "error": result.stderr.decode('utf-8', errors='replace')[:500],
                "raw_file": str(out_path),
            }
        out_path.write_bytes(result.stdout)
        return {
            "status": "quarantined",
            "raw_file": str(out_path.resolve()),
            "stderr": result.stderr.decode('utf-8', errors='replace')[:500] or None,
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout (90s)", "raw_file": outfile}
    except Exception as e:
        return {"error": str(e)[:200], "raw_file": outfile}


def main():
    parser = argparse.ArgumentParser(description='Gather all morning briefing data')
    parser.add_argument('--outlook-requests', help='Playwright network dump from Outlook Web (required on Mac/Linux, optional on Windows)')
    parser.add_argument('--teams-requests', help='Playwright network dump from Teams')
    parser.add_argument('--date', help='Date YYYY-MM-DD (default: today)')
    parser.add_argument('--teams-from', help='Teams messages from (default: yesterday 18:00)')
    parser.add_argument('--email-raw-out', help='Quarantine raw email JSON to this file instead of returning it in stdout')
    args = parser.parse_args()

    date = args.date or datetime.now().strftime('%Y-%m-%d')

    if args.teams_from:
        teams_from = args.teams_from
    else:
        yesterday = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        teams_from = f"{yesterday}T18:00"

    outlook_token = None
    if args.outlook_requests:
        resolved_outlook = resolve_request_file(args.outlook_requests)
        if not resolved_outlook:
            print(json.dumps({
                "error": (
                    f"Outlook requests file not found: {args.outlook_requests}. "
                    "Pass the absolute path or just the basename if Playwright saved it under its own root."
                )
            }), file=sys.stderr)
            sys.exit(1)

        outlook_token = extract_token(resolved_outlook, 'outlook.office.com')
        if not outlook_token:
            outlook_token = extract_token(resolved_outlook, 'outlook.cloud.microsoft')
        if not outlook_token:
            print("WARNING: --outlook-requests provided but no token found in dump file.", file=sys.stderr)

    use_com = IS_WINDOWS and not outlook_token
    if not IS_WINDOWS and not outlook_token:
        print(json.dumps({"error": "No Outlook token found. On Mac/Linux, --outlook-requests is required."}), file=sys.stderr)
        sys.exit(1)

    teams_token = None
    if args.teams_requests:
        resolved_teams = resolve_request_file(args.teams_requests)
        if not resolved_teams:
            print(json.dumps({
                "error": (
                    f"Teams requests file not found: {args.teams_requests}. "
                    "Pass the absolute path or just the basename if Playwright saved it under its own root."
                )
            }), file=sys.stderr)
            sys.exit(1)

        teams_token = extract_token(resolved_teams, 'chatsvc')
        if not teams_token:
            print("WARNING: --teams-requests provided but no IC3 token found in dump file.", file=sys.stderr)

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    if outlook_token:
        env['DAYOPS_OUTLOOK_TOKEN'] = outlook_token
    if teams_token:
        env['DAYOPS_TEAMS_TOKEN'] = teams_token

    cal_script = os.path.join(SCRIPTS_DIR, 'gather_calendar.py')
    email_script = os.path.join(SCRIPTS_DIR, 'gather_email.py')
    todo_script = os.path.join(SCRIPTS_DIR, 'gather_todo.py')
    teams_script = os.path.join(SCRIPTS_DIR, 'gather_teams.py')

    tasks = []

    if use_com:
        tasks.append(([cal_script, date], 'calendar'))
    else:
        tasks.append(([cal_script, '--token', 'env', date], 'calendar'))

    if outlook_token:
        tasks.append(([todo_script, '--token', 'env'], 'todo'))

    if teams_token:
        tasks.append(([teams_script, '--token', 'env', '--from', teams_from, '--deep'], 'teams'))

    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run_script, script_args, label, env): label for script_args, label in tasks}
        for future in as_completed(futures):
            label, data = future.result()
            results[label] = data

    if use_com:
        email_args = [email_script]
    else:
        email_args = [email_script, '--token', 'env']

    if args.email_raw_out:
        results['email'] = run_email_to_file(email_args, args.email_raw_out, env)
    else:
        _, results['email'] = run_script(email_args, 'email', env)

    output = {
        'date': date,
        'teams_from': teams_from,
        'mode': 'com' if use_com else 'http',
        'sources': {
            'calendar': 'com' if use_com else 'http',
            'email': 'quarantined' if args.email_raw_out else ('com' if use_com else 'http'),
            'todo': 'http' if outlook_token else 'skipped',
            'teams': 'http' if teams_token else 'skipped',
        },
        'calendar': results.get('calendar', {"error": "not run"}),
        'email': results.get('email', {"error": "not run"}),
        'todo': results.get('todo', {"error": "skipped - no outlook token"}),
        'teams': results.get('teams', {"error": "skipped - no teams token"}),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
