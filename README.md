# Personal Optimization

My personal AI automation stack - built with Claude, GitHub Actions, and Google APIs.

## What's in here

### Daily Digest (`scripts/daily_digest.py`)
Automated morning briefing that runs every day at 6am GMT via GitHub Actions. Pulls my Google Calendar events, generates a personalised digest using the Claude API, and sends it to both my personal and work email. Also creates a calendar event with the full digest in the notes.

**Stack:** GitHub Actions + Claude API (claude-opus-4-5) + Google Calendar API + Gmail API

### AI Activity Log (`ai-activity-log.md`)
Running log of every meaningful AI project I've built or used. Tracks why I did it, what I built, how I did it, and the outcome. High-level enough to explain to anyone.

### Scripts (`scripts/`)
- `daily_digest.py` - main digest script
- `auth_setup.py` - one-time Google OAuth setup (do not commit credentials.json or token.json)

## Setup
Requires the following GitHub Secrets:
- `ANTHROPIC_API_KEY` - from console.anthropic.com
- `GOOGLE_TOKEN` - generated via auth_setup.py

## Running manually
```bash
export GOOGLE_TOKEN=$(cat ~/Personal-Optimization/scripts/token.json)
python3 ~/Personal-Optimization/scripts/daily_digest.py
```
