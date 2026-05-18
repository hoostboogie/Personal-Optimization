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

New concepts already covered (do not reuse these terms):
{_bullets([e["term"] for e in history["newConcepts"]])}

Keep In Mind items to SUPPRESS entirely (shown 5+ consecutive days — omit these):
{_bullets(suppressed_keep_in_mind)}"""

# ── Rotating 5th sport topic by season ───────────────────────────────────────
_month = datetime.now().month
if _month in (1, 5, 6, 7, 8, 9):
    # Jan = Australian Open; May-Jun = French Open; Jul = Wimbledon; Aug-Sep = US Open
    sport5_query = "tennis latest news today"
    sport5_label = "tennis"
elif _month in (4,):
    sport5_query = "NBA playoffs latest news today"
    sport5_label = "NBA playoffs"
else:
    # Oct-Mar, Dec: NBA regular season
    sport5_query = "NBA latest news today"
    sport5_label = "NBA"

# ── Weekday concept theme ─────────────────────────────────────────────────────
CONCEPT_THEMES = {
    0: "sustainability methodology",   # Monday
    1: "AI or machine learning",       # Tuesday
    2: "media or adtech",              # Wednesday
    3: "finance or M&A",              # Thursday
    4: "philosophy or systems thinking", # Friday
    5: "climate science",              # Saturday
    6: "environmental policy",         # Sunday
}
concept_theme = CONCEPT_THEMES[datetime.now().weekday()]

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

Use the web_search tool to ground the TOP NEWS and TODAY'S NEW CONCEPT sections with real, current information before writing them. For TOP NEWS, run these 5 searches:
1. "UK politics news today"
2. "US politics news today"
3. "Arsenal FC latest"
4. "New York Yankees latest"
5. "{sport5_query}"

For TODAY'S NEW CONCEPT, run 1 search: "{concept_theme} concept worth knowing today"

Format the email exactly as follows. Do not add extra sections or change the order.

GOOD MORNING, JUSTIN

✨ QUOTE

One short, non-cliché quote with attribution. Nothing that sounds like LinkedIn.
Format: "quote text" — Author Name

📰 TOP NEWS (5 bullets max)

Based on your web searches above, write one specific, current headline per topic: UK politics, US politics, Arsenal FC, New York Yankees, {sport5_label}. Format each bullet as: - [Headline summary](source_url)

📅 TODAY'S AGENDA

For each calendar event listed above:
- Time and title
- 1-2 lines of useful context: who's likely involved, what the goal probably is, or any relevant background

🧠 KEEP IN MIND

2-3 reminders for things not on the calendar worth keeping front of mind. Draw from context about Justin's life: Cedara role, Propagation Nation, personal goals, Arsenal season, open financial decisions. Use bullet points. Skip any items listed under "Keep In Mind items to SUPPRESS" above.

🧩 TODAY'S NEW CONCEPT

Theme today: {concept_theme}
Based on your web search, pick one term or concept in this area that is genuinely worth knowing. It must NOT be any term already in the "New concepts already covered" list above.
Format:
**Term**: ~3 sentence explanation of what it is and why it matters.
[Source title](source_url)

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
    max_tokens=2500,
    tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
    messages=[{"role": "user", "content": prompt}],
)

# With tool use, the final answer is always the last text block in content
digest_content = next(
    (block.text for block in reversed(message.content) if hasattr(block, "text")),
    "",
)

# ── Extract items from digest for history ─────────────────────────────────────
_SECTION_RE = r"(?:📰|📅|🧠|🧩|🌍|💡|😄|✨)"

def _extract_section(text, emoji):
    pattern = rf"{re.escape(emoji)}[^\n]*\n+(.*?)(?=\n{_SECTION_RE}|\Z)"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""

quote_text   = _extract_section(digest_content, "✨")
joke_text    = _extract_section(digest_content, "😄")
fact_text    = _extract_section(digest_content, "💡")
env_text     = _extract_section(digest_content, "🌍")
kim_text     = _extract_section(digest_content, "🧠")
concept_text = _extract_section(digest_content, "🧩")

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

# Extract concept term (first **bold** word or first line as fallback)
if concept_text:
    term_match = re.search(r"\*\*([^*]+)\*\*", concept_text)
    term = term_match.group(1).strip() if term_match else concept_text.splitlines()[0][:60]
    history["newConcepts"].append({"term": term, "date": TODAY})

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

# Convert markdown links [text](url) to HTML anchors for the HTML part
def md_links_to_html(text):
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

html_body = md_links_to_html(digest_content)
html_content = f"<pre style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;'>{html_body}</pre>"
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
