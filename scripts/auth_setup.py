from google_auth_oauthlib.flow import InstalledAppFlow
import json
import os

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets.readonly'
]

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

flow = InstalledAppFlow.from_client_secrets_file(
    os.path.expanduser('~/Personal-Optimization/scripts/credentials.json'), SCOPES)
creds = flow.run_local_server(port=0, prompt='consent', access_type='offline')

token_data = {
    'token': creds.token,
    'refresh_token': creds.refresh_token,
    'token_uri': creds.token_uri,
    'client_id': creds.client_id,
    'client_secret': creds.client_secret,
    'scopes': list(creds.scopes)
}

with open(os.path.expanduser('~/Personal-Optimization/scripts/token.json'), 'w') as f:
    json.dump(token_data, f)

print("Done! Scopes granted:", creds.scopes)
