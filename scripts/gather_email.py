"""Gather unread emails from Outlook with noise filtering.

Usage:
    python scripts/gather_email.py                        # unread (COM)
    python scripts/gather_email.py --token TOKEN           # unread (HTTP)
    python scripts/gather_email.py --max 20                # limit results

On Windows with Outlook desktop: no --token needed (uses COM).
On Mac/Linux: pass --token captured from Outlook Web via Playwright.

Outputs JSON to stdout. Separates emails, meeting invites, and noise.
"""
import sys
import os
import json
import re
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.utils import get_outlook, output_json, api_get, strip_html, tag_untrusted


# Default noise filters — user can override via profile
DEFAULT_NOISE_PATTERNS = [
    {'sender_contains': 'gitlab', 'action': 'ignore', 'reason': 'Duplicated in Teams'},
    {'sender_contains': 'confluence', 'subject_contains': 'digest', 'action': 'low_priority', 'reason': 'Automated digest'},
    {'sender_contains': '(Jira)', 'action': 'summarize', 'reason': 'Jira notification'},
    {'sender_contains': '[JIRA]', 'action': 'summarize', 'reason': 'Jira notification'},
    {'sender_contains': 'Jira]', 'action': 'summarize', 'reason': 'Jira notification (any instance)'},
]


def matches_noise_filter(sender, subject, filters):
    """Check if an email matches any noise filter. Returns (action, reason) or None."""
    sender_lower = sender.lower()
    subject_lower = subject.lower()

    for f in filters:
        sender_match = f.get('sender_contains', '').lower() in sender_lower if f.get('sender_contains') else True
        subject_match = f.get('subject_contains', '').lower() in subject_lower if f.get('subject_contains') else True

        if sender_match and subject_match:
            return f['action'], f.get('reason', '')

    return None


def load_noise_filters(profile_path=None):
    """Load noise filters from user profile, fall back to defaults."""
    if profile_path and os.path.exists(profile_path):
        try:
            import yaml
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = yaml.safe_load(f)
            return profile.get('noise_filters', DEFAULT_NOISE_PATTERNS)
        except Exception:
            pass
    return DEFAULT_NOISE_PATTERNS


def get_emails_http(token, max_results=30):
    """Fetch unread emails via Outlook REST API.

    Returns raw items list from Inbox only.

    Security: limit the briefing surface area to unread Inbox mail so we do
    not ingest stale unread items from Archive/Junk-like folders into the
    prompt context.

    Uses @odata.type and MeetingMessageType instead of COM's ItemClass for
    message classification.
    """
    url = (
        "https://outlook.office.com/api/v2.0/me/mailfolders/inbox/messages"
        "?$filter=isRead%20eq%20false"
        f"&$top={min(max_results * 3, 100)}"
        "&$orderby=ReceivedDateTime%20desc"
    )
    data = api_get(url, token)
    if 'error' in data:
        return []
    return data.get('value', [])


def process_noise_and_jira(sender, subject, noise_filters, noise, jira_summaries):
    """Apply noise filters. Returns True if item was filtered (caller should skip)."""
    noise_result = matches_noise_filter(sender, subject, noise_filters)
    if noise_result:
        action, reason = noise_result
        if action == 'ignore':
            noise.append({'sender': sender, 'subject': subject, 'action': action, 'reason': reason})
            return True
        elif action == 'summarize':
            ticket_match = re.search(r'[A-Z][\w]+-\d+', subject)
            ticket_key = ticket_match.group() if ticket_match else subject
            if ticket_key not in jira_summaries:
                jira_summaries[ticket_key] = {'count': 0, 'latest_subject': subject, 'senders': set()}
            jira_summaries[ticket_key]['count'] += 1
            jira_summaries[ticket_key]['senders'].add(sender)
            jira_summaries[ticket_key]['latest_subject'] = subject
            return True
        elif action == 'low_priority':
            noise.append({'sender': sender, 'subject': subject, 'action': action, 'reason': reason})
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description='Gather unread emails')
    parser.add_argument('--max', type=int, default=30, help='Max email results')
    parser.add_argument('--token', help='Outlook REST API Bearer token (non-Windows)')
    args = parser.parse_args()

    # Resolve token: "env" means read from DAYOPS_OUTLOOK_TOKEN env var
    token = args.token
    if token == 'env':
        token = os.environ.get('DAYOPS_OUTLOOK_TOKEN')

    noise_filters = load_noise_filters('user-profile.yaml')

    emails = []
    meeting_invites = []
    meeting_cancellations = []
    noise = []
    jira_summaries = {}

    if token:
        # HTTP path (Mac/Linux)
        raw_items = get_emails_http(token, args.max)
        count = 0
        for item in raw_items:
            sender = item.get('Sender', {}).get('EmailAddress', {}).get('Name', '?')
            subject = item.get('Subject', '')
            received = item.get('ReceivedDateTime', '')[:16].replace('T', ' ')

            # Classify using @odata.type and MeetingMessageType (REST API equivalents of COM ItemClass)
            odata_type = item.get('@odata.type', '')
            meeting_type = item.get('MeetingMessageType', '')

            is_meeting_msg = 'MeetingMessage' in odata_type or meeting_type

            if is_meeting_msg:
                if meeting_type == 'MeetingRequest':
                    body = strip_html(item.get('Body', {}).get('Content', ''))
                    meeting_invites.append({
                        'sender': sender, 'subject': tag_untrusted(subject, 'email'), 'received': received,
                        'body_preview': tag_untrusted(body[:300], 'email'),
                    })
                    continue
                elif meeting_type == 'MeetingCancelled' or 'Canceled' in subject or 'Cancelled' in subject:
                    meeting_cancellations.append({
                        'sender': sender, 'subject': tag_untrusted(subject, 'email'), 'received': received,
                    })
                    continue
                else:
                    continue

            if process_noise_and_jira(sender, subject, noise_filters, noise, jira_summaries):
                continue

            to_field = '; '.join(r.get('EmailAddress', {}).get('Name', '') for r in item.get('ToRecipients', []))
            cc_field = '; '.join(r.get('EmailAddress', {}).get('Name', '') for r in item.get('CcRecipients', []))
            body = strip_html(item.get('Body', {}).get('Content', ''))

            emails.append({
                'sender': sender, 'subject': tag_untrusted(subject, 'email'), 'received': received,
                'to': to_field[:100], 'cc': cc_field[:100], 'body_preview': tag_untrusted(body[:300], 'email'),
            })

            count += 1
            if count >= args.max:
                break
    else:
        # COM path (Windows)
        ns = get_outlook()
        inbox = ns.GetDefaultFolder(6)
        items = inbox.Items
        items.Sort('[ReceivedTime]', True)

        count = 0
        for i in range(min(100, items.Count)):
            msg = items[i]
            if not msg.UnRead:
                continue

            msg_class = msg.MessageClass
            sender = msg.SenderName
            subject = msg.Subject
            received = str(msg.ReceivedTime)[:16]

            if msg_class == 'IPM.Schedule.Meeting.Request':
                body = (msg.Body[:500] if msg.Body else '').strip()
                meeting_invites.append({
                    'sender': sender, 'subject': tag_untrusted(subject, 'email'), 'received': received,
                    'body_preview': tag_untrusted(body[:300], 'email'),
                })
                continue

            if 'IPM.Schedule.Meeting.Canceled' in msg_class:
                meeting_cancellations.append({
                    'sender': sender, 'subject': tag_untrusted(subject, 'email'), 'received': received,
                })
                continue

            if 'IPM.Schedule.Meeting.Resp' in msg_class:
                continue

            if msg_class != 'IPM.Note':
                continue

            if process_noise_and_jira(sender, subject, noise_filters, noise, jira_summaries):
                continue

            to_field = msg.To if hasattr(msg, 'To') else ''
            cc_field = msg.CC if hasattr(msg, 'CC') else ''
            body = (msg.Body[:500] if msg.Body else '').strip()

            emails.append({
                'sender': sender, 'subject': tag_untrusted(subject, 'email'), 'received': received,
                'to': to_field[:100], 'cc': cc_field[:100], 'body_preview': tag_untrusted(body[:300], 'email'),
            })

            count += 1
            if count >= args.max:
                break

    jira_summary_list = []
    for ticket, info in jira_summaries.items():
        jira_summary_list.append({
            'ticket': ticket, 'update_count': info['count'],
            'latest_subject': info['latest_subject'], 'senders': list(info['senders']),
        })

    output_json({
        'emails': emails, 'email_count': len(emails),
        'meeting_invites': meeting_invites,
        'meeting_cancellations': meeting_cancellations,
        'jira_summaries': jira_summary_list,
        'noise_filtered': len(noise), 'noise': noise,
    })


if __name__ == '__main__':
    main()
