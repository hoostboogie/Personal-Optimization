import os
import json
import re
import anthropic
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Dedup history ─────────────────────────────────────────────────────────────
HISTORY_FILE = "data/digest_history.json"
TODAY        = datetime.now().strftime("%Y-%m-%d")
CUTOFF       = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

def load_history():
    empty = {
        "quotes":            [],
        "jokes":             [],
        "funFacts":          [],
        "envNews":           [],
        "newConcepts":       [],
        "keepInMindHistory": [],
    }
    if not os.path.exists(HISTORY_FILE):
        return empty
    with open(HISTORY_FILE) as f:
        h = json.load(f)
    for key in ("quotes", "jokes", "funFacts", "envNews", "newConcepts"):
        h.setdefault(key, [])
        h[key] = [e for e in h[key] if e.get("date", "") >= CUTOFF]
    h.setdefault("keepInMindHistory", [])
    return h

def save_history(h):
    os.makedirs("data", exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, indent=2)

history = load_history()

# Items shown 5+ consecutive days with no state change — tell Claude to skip them
suppressed_keep_in_mind = [
    e["item"] for e in history["keepInMindHistory"] if e.get("daysShown", 0) >= 5
]

def _bullets(items):
    return "\n".join(f"  - {i}" for i in items) if items else "  (none yet)"

dedup_block = f"""[DEDUP — do not repeat any of these recently used items]

Quotes used in the last 60 days (do not reuse):
{_bullets([f'"{e["text"]}" — {e["author"]}' for e in history["quotes"]])}

Jokes used (do not reuse):
{_bullets([e["text"][:100] for e in history["jokes"]])}

Fun facts used (do not reuse):
{_bullets([e["text"][:100] for e in history["funFacts"]])}

Environmental news topics used (do not reuse):
{_bullets([e["summary"][:100] for e in history["envNews"]])}

Keep In Mind items to SUPPRESS entirely (shown 5+ consecutive days — omit these):
{_bullets(suppressed_keep_in_mind)}"""

# ── Auth ──────────────────────────────────────────────────────────────────────
token_data = json.loads(os.environ["GOOGLE_TOKEN"])
creds = Credentials(
    token=token_data["token"],
    refresh_token=token_data["refresh_token"],
    token_uri=token_data["token_uri"],
    client_id=token_data["client_id"],
    client_secret=token_data["client_secret"],
    scopes=token_data["scopes"],
)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())

# ── Google Calendar ───────────────────────────────────────────────────────────
calendar_service = build("calendar", "v3", credentials=creds)
now   = datetime.utcnow()
start = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
end   = now.replace(hour=23, minute=59, second=59).isoformat() + "Z"
events_result = calendar_service.events().list(
    calendarId="primary",
    timeMin=start,
    timeMax=end,
    singleEvents=True,
    orderBy="startTime",
).execute()

event_list = []
for e in events_result.get("items", []):
    start_time = e["start"].get("dateTime", e["start"].get("date", ""))
    if "T" in start_time:
        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        time_str = dt.strftime("%H:%M GMT")
    else:
        time_str = "All day"
    event_list.append(
        f"{time_str} - {e.get('summary', 'No title')}: {e.get('description', e.get('location', ''))}"
    )

events_text = "\n".join(event_list) if event_list else "No events today"

# ── Generate digest ───────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
today  = datetime.now().strftime("%A, %d %B %Y")

prompt = f"""Generate a daily digest email for Justin Bogdanski for {today}.

Today's calendar events:
{events_text}

{dedup_block}

Format the email exactly as follows. Do not add extra sections or change the order.

GOOD MORNING, JUSTIN

✨ QUOTE

One short, non-cliché quote with attribution. Nothing that sounds like LinkedIn.
Format: "quote text" — Author Name

📰 TOP NEWS (5 bullets max)

Current headlines across: UK politics, US politics, Arsenal FC, New York Yankees, professional tennis, and active global conflicts. One line per story, no filler. Be specific and current.

📅 TODAY'S AGENDA

For each calendar event listed above:
- Time and title
- 1-2 lines of useful context: who's likely involved, what the goal probably is, or any relevant background

🧠 KEEP IN MIND

2-3 reminders for things not on the calendar or task list worth keeping front of mind. Draw from context about Justin's life: Cedara role, Propagation Nation, personal goals, Arsenal season, open financial decisions. Use bullet points. Skip any items listed under "Keep In Mind items to SUPPRESS" above.

🌍 GOOD ENVIRONMENTAL NEWS

One piece of genuinely positive environmental news from the past 48 hours. Real and specific.

💡 FUN FACT

One genuinely interesting fact. Rotate topics widely.

😄 JOKE

One short, actually funny joke. Dry wit preferred.

---

{today}"""

message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=2000,
    messages=[{"role": "user", "content": prompt}],
)
digest_content = message.content[0].text

# ── Extract items from digest for history ─────────────────────────────────────
_SECTION_RE = r"(?:📰|📅|🧠|🌍|💡|😄|✨)"

def _extract_section(text, emoji):
    pattern = rf"{re.escape(emoji)}[^\n]*\n+(.*?)(?=\n{_SECTION_RE}|\Z)"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""

quote_text = _extract_section(digest_content, "✨")
joke_text  = _extract_section(digest_content, "😄")
fact_text  = _extract_section(digest_content, "💡")
env_text   = _extract_section(digest_content, "🌍")
kim_text   = _extract_section(digest_content, "🧠")

q_match = re.search(r'"([^"]+)"\s*[—\-]\s*(.+)', quote_text)
if q_match:
    history["quotes"].append({
        "text": q_match.group(1).strip(),
        "author": q_match.group(2).strip(),
        "date": TODAY,
    })

if joke_text:
    history["jokes"].append({"text": joke_text[:200], "date": TODAY})
if fact_text:
    history["funFacts"].append({"text": fact_text[:200], "date": TODAY})
if env_text:
    history["envNews"].append({"summary": env_text[:200], "date": TODAY})

# Keep In Mind: track consecutive days shown; prune items missing from today's output
today_items = {
    re.sub(r"^[-•*·]\s*", "", line).strip()
    for line in kim_text.splitlines()
    if re.match(r"^\s*[-•*·]\s+", line)
}
today_items.discard("")

seen = set()
updated_kim = []
for entry in history["keepInMindHistory"]:
    if entry["item"] in today_items:
        entry["daysShown"] = entry.get("daysShown", 0) + 1
        seen.add(entry["item"])
        updated_kim.append(entry)
    # items absent from today's output are dropped (pruned or naturally cycled out)

for item in today_items - seen:
    updated_kim.append({"item": item, "daysShown": 1, "lastChanged": TODAY})

history["keepInMindHistory"] = updated_kim
save_history(history)

# ── Send email ────────────────────────────────────────────────────────────────
gmail_service = build("gmail", "v1", credentials=creds)
msg = MIMEMultipart("alternative")
msg["Subject"] = f"Daily Digest - {today}"
msg["From"]    = "justin.bogdanski@cedara.io"
msg["To"]      = "jbbogdanski@gmail.com, justin.bogdanski@cedara.io"

html_content = f"<pre style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;'>{digest_content}</pre>"
msg.attach(MIMEText(digest_content, "plain"))
msg.attach(MIMEText(html_content, "html"))

raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
gmail_service.users().messages().send(userId="me", body={"raw": raw}).execute()

# ── Create calendar event ─────────────────────────────────────────────────────
event = {
    "summary": "Daily Digest",
    "description": digest_content,
    "start": {
        "dateTime": now.replace(hour=6, minute=0, second=0).isoformat() + "Z",
        "timeZone": "Europe/London",
    },
    "end": {
        "dateTime": now.replace(hour=6, minute=15, second=0).isoformat() + "Z",
        "timeZone": "Europe/London",
    },
}
calendar_service.events().insert(calendarId="primary", body=event).execute()

print(f"Digest sent and calendar event created for {today}")
