"""Gather and manage Microsoft To Do tasks using a captured Substrate token.

Usage:
    python scripts/gather_todo.py --token TOKEN                         # list all tasks
    python scripts/gather_todo.py --token TOKEN --folder Inbox          # tasks from specific folder
    python scripts/gather_todo.py --token TOKEN --create "Buy milk"     # create task in Inbox
    python scripts/gather_todo.py --token TOKEN --create "Review PR" --folder "Focus ≤30m"

The token is captured by Playwright from To Do web (audience: outlook.office.com).
Outputs JSON to stdout.
"""
import sys
import os
import json
import argparse
import urllib.request
import urllib.error
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.utils import tag_untrusted, DIRECT_OPENER

BASE_URL = "https://substrate.office.com/todob2/api/v1"


def api_request(url, token, method='GET', body=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode('utf-8') if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with DIRECT_OPENER.open(req, timeout=15) as resp:
            if resp.status == 204:
                return {"status": "deleted"}
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode('utf-8', errors='replace')[:200]}


def get_folders(token):
    url = f"{BASE_URL}/taskfolders?maxpagesize=50"
    return api_request(url, token)


def get_tasks(token, folder_id, max_count=50):
    url = f"{BASE_URL}/taskfolders/{folder_id}/tasks?maxpagesize={max_count}"
    return api_request(url, token)


def create_task(token, folder_id, subject, body=None):
    url = f"{BASE_URL}/taskfolders/{folder_id}/tasks"
    task_body = {"Subject": subject}
    if body:
        task_body["Body"] = {"ContentType": "Text", "Content": body}
    return api_request(url, token, method='POST', body=task_body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--token', required=True, help='Substrate Bearer token from To Do web')
    parser.add_argument('--folder', default=None, help='Folder name to list tasks from (default: all)')
    parser.add_argument('--create', default=None, help='Create a task with this subject')
    parser.add_argument('--body', default=None, help='Task body/description (used with --create)')
    args = parser.parse_args()

    # Resolve token: "env" means read from DAYOPS_OUTLOOK_TOKEN env var
    token = args.token
    if token == 'env':
        token = os.environ.get('DAYOPS_OUTLOOK_TOKEN')
    if not token:
        print(json.dumps({"error": "No token provided"}), file=sys.stderr)
        return

    # Get folders
    folder_data = get_folders(token)
    if 'error' in folder_data:
        print(json.dumps(folder_data, indent=2))
        return

    folders = folder_data.get('Value', [])
    folder_map = {f['Name']: f['Id'] for f in folders}

    # Create task
    if args.create:
        target_folder = args.folder or 'Inbox'
        folder_id = folder_map.get(target_folder)
        if not folder_id:
            print(json.dumps({"error": f"Folder '{target_folder}' not found. Available: {list(folder_map.keys())}"}))
            return
        result = create_task(token, folder_id, args.create, args.body)
        print(json.dumps({
            "action": "created",
            "subject": result.get("Subject", "?"),
            "folder": target_folder,
            "id": result.get("Id", "?"),
            "status": result.get("Status", "?"),
        }, ensure_ascii=False, indent=2))
        return

    # List tasks
    output_folders = []
    for f in folders:
        if args.folder and f['Name'] != args.folder:
            continue

        tasks_data = get_tasks(token, f['Id'])
        tasks = []
        for t in tasks_data.get('Value', []):
            if t.get('Status') == 'Completed':
                continue
            tasks.append({
                'subject': tag_untrusted(t.get('Subject', '?'), 'todo'),
                'status': t.get('Status', '?'),
                'importance': t.get('Importance', '?'),
                'due': t.get('DueDateTime', {}).get('DateTime', '') if t.get('DueDateTime') else None,
                'created': t.get('CreatedDateTime', '')[:10] if t.get('CreatedDateTime') else None,
            })

        if tasks:
            output_folders.append({
                'folder': f['Name'],
                'task_count': len(tasks),
                'tasks': tasks,
            })

    print(json.dumps({
        'total_folders': len(folders),
        'folders_with_tasks': len(output_folders),
        'folders': output_folders,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
