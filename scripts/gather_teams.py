"""Gather Teams chat messages using a captured IC3 token.

Usage:
    python scripts/gather_teams.py --token TOKEN                    # today's chats
    python scripts/gather_teams.py --token TOKEN --hours 24         # last 24h
    python scripts/gather_teams.py --token TOKEN --conv-id ID       # specific conversation

The token is captured by Playwright from Teams web (audience: ic3.teams.office.com).
Outputs JSON to stdout.
"""
import sys
import os
import json
import re
import argparse
from datetime import datetime, timedelta
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.utils import strip_html, tag_untrusted, DIRECT_OPENER

BASE_URL = "https://teams.cloud.microsoft/api/chatsvc/emea/v1"
HEADERS_BASE = {
    "behavioroverride": "redirectAs404",
    "Referer": "https://teams.cloud.microsoft/",
}


def api_get(url, token):
    headers = {**HEADERS_BASE, "Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with DIRECT_OPENER.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode('utf-8', errors='replace')[:200]}


def get_conversations(token, max_count=30):
    url = f"{BASE_URL}/users/ME/conversations?view=msnp24Equivalent&pageSize={max_count}&startTime=1"
    return api_get(url, token)


def get_messages(token, conv_id, page_size=200):
    url = f"{BASE_URL}/users/ME/conversations/{conv_id}/messages?view=msnp24Equivalent&pageSize={page_size}"
    return api_get(url, token)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--token', required=True, help='IC3 Bearer token from Teams web')
    parser.add_argument('--hours', type=int, default=None, help='Look back N hours (default: 24)')
    parser.add_argument('--from', dest='date_from', help='Start date/time: YYYY-MM-DD or YYYY-MM-DDTHH:MM')
    parser.add_argument('--to', dest='date_to', help='End date/time: YYYY-MM-DD or YYYY-MM-DDTHH:MM (default: now)')
    parser.add_argument('--conv-id', help='Specific conversation ID to pull messages from')
    parser.add_argument('--max-convs', type=int, default=30, help='Max conversations to scan')
    parser.add_argument('--deep', action='store_true', help='Pull ALL messages from active conversations (not just last message).')
    args = parser.parse_args()

    # Resolve token: "env" means read from DAYOPS_TEAMS_TOKEN env var
    token = args.token
    if token == 'env':
        token = os.environ.get('DAYOPS_TEAMS_TOKEN')
    if not token:
        print(json.dumps({"error": "No token provided"}))
        return

    # Determine time window
    now = datetime.now(tz=None)
    if args.date_from:
        # Parse --from (supports YYYY-MM-DD or YYYY-MM-DDTHH:MM)
        fmt = '%Y-%m-%dT%H:%M' if 'T' in args.date_from else '%Y-%m-%d'
        cutoff = datetime.strptime(args.date_from, fmt)
        if args.date_to:
            fmt2 = '%Y-%m-%dT%H:%M' if 'T' in args.date_to else '%Y-%m-%d'
            end = datetime.strptime(args.date_to, fmt2)
            if fmt2 == '%Y-%m-%d':
                end = end.replace(hour=23, minute=59)
        else:
            end = now
    else:
        hours = args.hours or 24
        cutoff = now - timedelta(hours=hours)
        end = now

    cutoff_str = cutoff.strftime('%Y-%m-%dT%H:%M')
    end_str = end.strftime('%Y-%m-%dT%H:%M')

    if args.conv_id:
        # Pull messages from a specific conversation (supports --from/--to filtering)
        data = get_messages(token, args.conv_id)
        messages = []
        for msg in data.get('messages', []):
            if msg.get('messagetype') not in ('RichText/Html', 'Text'):
                continue
            msg_time = msg.get('composetime', '')[:16]
            # Apply time filter if --from/--to provided
            if msg_time and msg_time < cutoff_str:
                continue
            if msg_time and msg_time > end_str:
                continue
            raw = msg.get('content', '')
            messages.append({
                'sender': msg.get('imdisplayname', '?'),
                'time': msg_time,
                'content': tag_untrusted(strip_html(raw)[:500], 'teams'),
                'has_mention': 'itemtype="http://schema.skype.com/Mention"' in raw,
            })
        messages.reverse()  # chronological order
        print(json.dumps({
            'conv_id': args.conv_id,
            'from': cutoff_str,
            'to': end_str,
            'message_count': len(messages),
            'messages': messages,
        }, ensure_ascii=False, indent=2))
        return

    # Scan all recent conversations
    conv_data = get_conversations(token, args.max_convs)
    if 'error' in conv_data:
        print(json.dumps(conv_data, indent=2))
        return

    conversations = []
    for conv in conv_data.get('conversations', []):
        conv_id = conv.get('id', '')
        if conv_id == '48:notifications':
            continue

        last_msg = conv.get('lastMessage', {})
        compose_time = last_msg.get('composetime', '')

        # In summary mode, filter conversations by their last message time
        # In deep mode, include any conversation that was active AFTER cutoff
        # (messages within the window are filtered per-message later)
        if not args.deep:
            if compose_time and compose_time[:16] < cutoff_str:
                continue
            if compose_time and compose_time[:16] > end_str:
                continue
        else:
            # For deep mode with date range: include conversations active after cutoff
            # (we can't know if they had messages on that exact date without pulling messages)
            if compose_time and compose_time[:16] < cutoff_str:
                continue

        props = conv.get('threadProperties', {})
        topic = props.get('topic', '')
        sender = last_msg.get('imdisplayname', '')
        content = strip_html(last_msg.get('content', ''))

        # Detect mentions of user
        raw_content = last_msg.get('content', '')
        has_mention = 'itemtype="http://schema.skype.com/Mention"' in raw_content

        conversations.append({
            'id': conv_id,
            'topic': tag_untrusted(topic, 'teams') if topic else '(1:1 chat)',
            'type': conv.get('type', ''),
            'last_sender': sender,
            'last_time': compose_time[:16],
            'last_message': tag_untrusted(content[:200], 'teams'),
            'has_mention': has_mention,
        })

    # Sort by time descending
    conversations.sort(key=lambda c: c['last_time'], reverse=True)

    if not args.deep:
        # Summary mode: just last message per conversation
        print(json.dumps({
            'mode': 'summary',
            'from': cutoff_str,
            'to': end_str,
            'conversations_with_activity': len(conversations),
            'conversations': conversations,
        }, ensure_ascii=False, indent=2))
        return

    # Deep mode: pull ALL messages from each active conversation within the time window
    deep_conversations = []
    for conv in conversations:
        conv_messages = get_messages(token, conv['id'], page_size=100)
        messages = []
        for msg in conv_messages.get('messages', []):
            if msg.get('messagetype') not in ('RichText/Html', 'Text'):
                continue
            msg_time = msg.get('composetime', '')[:16]
            if msg_time < cutoff_str:
                continue
            if msg_time > end_str:
                continue
            raw = msg.get('content', '')
            content = strip_html(raw)[:500]
            sender = msg.get('imdisplayname', '?')
            if not sender and not content.strip():
                continue
            messages.append({
                'sender': sender,
                'time': msg_time,
                'content': tag_untrusted(content, 'teams'),
                'has_mention': 'itemtype="http://schema.skype.com/Mention"' in raw,
            })

        if messages:
            messages.reverse()  # chronological order
            deep_conversations.append({
                'topic': conv['topic'],  # already tagged from summary pass
                'id': conv['id'],
                'message_count': len(messages),
                'messages': messages,
            })

    print(json.dumps({
        'mode': 'deep',
        'from': cutoff_str,
        'to': end_str,
        'conversations_scanned': len(conversations),
        'conversations_with_messages': len(deep_conversations),
        'total_messages': sum(c['message_count'] for c in deep_conversations),
        'conversations': deep_conversations,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
