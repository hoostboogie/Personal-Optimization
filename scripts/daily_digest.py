import os
import json
import anthropic
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Auth
token_data = json.loads(os.environ['GOOGLE_TOKEN'])
creds = Credentials(
    token=token_data['token'],
    refresh_token=token_data['refresh_token'],
    token_uri=token_data['token_uri'],
    client_id=token_data['client_id'],
    client_secret=token_data['client_secret'],
    scopes=token_data['scopes']
)

if creds.expired and creds.refresh_token:
    creds.refresh(Request())

# --- Google Calendar ---
calendar_service = build('calendar', 'v3', credentials=creds)
now = datetime.utcnow()
start = now.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
end = now.replace(hour=23, minute=59, second=59).isoformat() + 'Z'
events_result = calendar_service.events().list(
    calendarId='primary',
    timeMin=start,
    timeMax=end,
    singleEvents=True,
    orderBy='startTime'
).execute()

events = events_result.get('items', [])
event_list = []

for e in events:
    start_time = e['start'].get('dateTime', e['start'].get('date', ''))
    if 'T' in start_time:
        dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        time_str = dt.strftime('%H:%M GMT')
    else:
        time_str = 'All day'
    event_list.append(f"{time_str} - {e.get('summary', 'No title')}: {e.get('description', e.get('location', ''))}")

events_text = '\n'.join(event_list) if event_list else 'No events today'

# --- Google Sheets: Justin's Tasks ---
SPREADSHEET_ID = '1DNwTNuNhs79onm1Ds7TXddEPbkObw23hLXkYQiKUoNA'
TARGET_GID = 913147250

sheets_service = build('sheets', 'v4', credentials=creds)

# Find the sheet name by gid
spreadsheet_meta = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
sheet_name = None
for sheet in spreadsheet_meta['sheets']:
    if sheet['properties']['sheetId'] == TARGET_GID:
        sheet_name = sheet['properties']['title']
        break

tasks_text = 'No tasks found'
if sheet_name:
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'"
    ).execute()
    rows = result.get('values', [])
    if rows:
        # First row is treated as headers, remaining rows are data
        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []
        task_lines = []
        for row in data_rows:
            if any(cell.strip() for cell in row if cell):  # skip empty rows
                # Zip with headers for context, fall back to raw values
                if headers:
                    task_parts = [f"{headers[i]}: {row[i]}" for i in range(min(len(headers), len(row))) if row[i].strip()]
                    task_lines.append(' | '.join(task_parts))
                else:
                    task_lines.append(' | '.join(cell for cell in row if cell.strip()))
        tasks_text = '\n'.join(task_lines) if task_lines else 'No tasks found'

# --- Generate digest with Claude ---
client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
today = datetime.now().strftime('%A, %d %B %Y')

prompt = f"""Generate a daily digest email for Justin Bogdanski for {today}.

Today's calendar events:
{events_text}

Justin's current task list (from his Google Sheet):
{tasks_text}

Format the email exactly like this, with real current information:

GOOD MORNING, JUSTIN

📰 TOP NEWS (5 bullets max)

Current headlines across: UK politics, US politics, Arsenal FC, New York Yankees, professional tennis, and active global conflicts. One line per story, no filler. Be specific and current.

📅 TODAY'S AGENDA

For each calendar event listed above:

- Time and title

- 1-2 lines of useful context: who's likely involved, what the goal probably is, or any relevant background

✅ TASKS & OPEN LOOPS

Based on Justin's task list above, surface the 3-5 most important or time-sensitive items. For each:
- Task name
- One line: why it matters today or what the next action is

If any tasks have deadlines approaching within 7 days, flag those first with 🚨.

🧠 KEEP IN MIND

2-3 reminders for things not on the calendar or task list worth keeping front of mind. Draw from context about Justin's life: Cedara role, Propagation Nation, personal goals, Arsenal season, open financial decisions.

🌍 GOOD ENVIRONMENTAL NEWS

One piece of genuinely positive environmental news from the past 48 hours. Real and specific.

💡 FUN FACT

One genuinely interesting fact. Rotate topics widely.

😄 JOKE

One short, actually funny joke. Dry wit preferred.

✨ QUOTE

One short non-cliché inspirational quote with attribution. Nothing that sounds like LinkedIn.

---

{today}"""

message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=2000,
    messages=[{"role": "user", "content": prompt}]
)

digest_content = message.content[0].text

# --- Send email ---
gmail_service = build('gmail', 'v1', credentials=creds)
msg = MIMEMultipart('alternative')
msg['Subject'] = f"Daily Digest - {today}"
msg['From'] = 'justin.bogdanski@cedara.io'
msg['To'] = 'jbbogdanski@gmail.com, justin.bogdanski@cedara.io'
html_content = f"<pre style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;'>{digest_content}</pre>"
msg.attach(MIMEText(digest_content, 'plain'))
msg.attach(MIMEText(html_content, 'html'))
raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
gmail_service.users().messages().send(userId='me', body={'raw': raw}).execute()

# --- Create calendar event ---
event = {
    'summary': 'Daily Digest',
    'description': digest_content,
    'start': {'dateTime': now.replace(hour=6, minute=0, second=0).isoformat() + 'Z', 'timeZone': 'Europe/London'},
    'end': {'dateTime': now.replace(hour=6, minute=15, second=0).isoformat() + 'Z', 'timeZone': 'Europe/London'},
}
calendar_service.events().insert(calendarId='primary', body=event).execute()

print(f"Digest sent and calendar event created for {today}")
