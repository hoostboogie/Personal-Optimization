"""
Alias detection helpers for Gmail threading.

Normalises sender display names to catch cases where the same person emails
from multiple addresses or with slightly different name formatting.
"""
import re

# All email addresses that belong to Justin
MY_ADDRESSES = {
    'jbbogdanski@gmail.com',
    'justin.bogdanski@cedara.io',
}

# Patterns in email address or display name that indicate non-human senders
_SKIP_EMAIL = (
    'noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'notification', 'newsletter', 'updates@', 'alerts@', 'mailer',
    'mailchimp', 'sendgrid', 'campaigns', 'bounce', 'unsubscribe',
    'github.com', 'venmo.com', 'auraframes.com', 'linkedin.com',
)
_SKIP_NAME = (
    'ctvc', 'programme team', 'impact programme', 'listserve',
    'linkedin', 'twitter', 'facebook', 'github actions', 'venmo',
    'aura frame', 'newsletter', 'daily digest', 'hoostboogie',
    'fin ai agent', 'no reply', 'noreply',
)


def is_human_sender(email: str, display_name: str = '') -> bool:
    """Return True if the sender looks like a real human, not a bot/newsletter/notification."""
    el = email.lower()
    nl = display_name.lower()
    if any(p in el for p in _SKIP_EMAIL):
        return False
    if any(p in nl for p in _SKIP_NAME):
        return False
    return True


def normalize_name(display_name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    name = display_name.lower()
    name = re.sub(r'[^\w\s]', '', name)
    return re.sub(r'\s+', ' ', name).strip()


def parse_from_header(header_value: str) -> tuple[str, str]:
    """
    Return (display_name, email) from a raw From header value.
    Handles both 'Name <email>' and bare 'email' formats.
    """
    m = re.match(r'^"?([^"<]+?)"?\s*<([^>]+)>\s*$', header_value.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip().lower()
    email = header_value.strip().lower()
    local = email.split('@')[0] if '@' in email else email
    return local, email


def is_from_me(header_value: str) -> bool:
    """True if the From header belongs to one of Justin's addresses."""
    _, email = parse_from_header(header_value)
    return email in MY_ADDRESSES


def last_sender_is_me(messages: list) -> bool:
    """True if the most recent message in a thread was sent by Justin."""
    if not messages:
        return False
    headers = _headers_dict(messages[-1])
    return is_from_me(headers.get('From', ''))


def thread_has_my_reply(messages: list) -> bool:
    """True if any message in the thread was sent by Justin."""
    for msg in messages:
        headers = _headers_dict(msg)
        if is_from_me(headers.get('From', '')):
            return True
    return False


def score_thread(messages: list, subject: str = '') -> int:
    """
    Simple priority score (higher = more important).
    Based on thread depth (relationship signal) + urgency cues in subject.
    """
    depth = len(messages)
    depth_score = 3 if depth >= 7 else (2 if depth >= 3 else 1)

    urgency_score = 0
    subj_lower = subject.lower()
    if '?' in subject:
        urgency_score += 1
    if any(w in subj_lower for w in ('urgent', 'asap', 'deadline', 'by eod', 'by monday',
                                      'by friday', 'by tomorrow', 'action required')):
        urgency_score += 1

    return depth_score + urgency_score


# ── Internal helpers ──────────────────────────────────────────────────────────

def _headers_dict(message: dict) -> dict:
    """Extract Gmail message headers as a flat {name: value} dict."""
    headers = message.get('payload', {}).get('headers', [])
    return {h['name']: h['value'] for h in headers}
