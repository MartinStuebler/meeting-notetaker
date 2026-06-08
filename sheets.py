"""Google Sheets output: OAuth desktop flow, create-if-missing, append a row.

Mirrors the Garden dashboard's OAuth pattern (personal_assistant/connectors/
google_auth.py), but scoped only for Sheets. One spreadsheet ("Interview
Tracker") holds one row per interview.

Auth is a one-time manual step: run `python sheets.py auth`, approve in the
browser, and a token.json is written. After that the Flask app refreshes the
token silently and never opens a browser.
"""

import glob
import os

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

HERE = os.path.dirname(os.path.abspath(__file__))

# Just Sheets: lets us create, read, and write spreadsheets we own.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

TOKEN_PATH = os.path.join(HERE, "token.json")
SHEET_ID_PATH = os.path.join(HERE, "sheet_id.txt")

SHEET_TITLE = "Interview Tracker"
HEADERS = ["Date", "Person", "Company", "Role", "Notes"]


class SheetsError(RuntimeError):
    pass


class NeedsAuth(SheetsError):
    pass


def _client_secret_path():
    matches = glob.glob(os.path.join(HERE, "client_secret*.json"))
    if not matches:
        raise SheetsError(
            "No client_secret*.json in the project. Download the OAuth desktop "
            "client JSON from Google Cloud and place it in this folder."
        )
    return matches[0]


def _load_token():
    if os.path.exists(TOKEN_PATH):
        return Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    return None


def _save_token(creds):
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())


def get_credentials(interactive=False):
    """Return valid creds. interactive=True runs the one-time browser consent."""
    creds = _load_token()
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
        return creds
    if not interactive:
        raise NeedsAuth(
            "Google Sheets is not authorized yet. In a terminal run:  "
            "./venv/bin/python sheets.py auth"
        )
    flow = InstalledAppFlow.from_client_secrets_file(_client_secret_path(), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    _save_token(creds)
    return creds


def _service():
    creds = get_credentials(interactive=False)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _load_sheet_id():
    if os.path.exists(SHEET_ID_PATH):
        return open(SHEET_ID_PATH).read().strip() or None
    return None


def _save_sheet_id(sid):
    with open(SHEET_ID_PATH, "w") as f:
        f.write(sid)


def _ensure_sheet(service):
    """Return the spreadsheet id, creating the sheet with headers if missing."""
    sid = _load_sheet_id()
    if sid:
        return sid
    created = service.spreadsheets().create(
        body={"properties": {"title": SHEET_TITLE}}
    ).execute()
    sid = created["spreadsheetId"]
    service.spreadsheets().values().update(
        spreadsheetId=sid, range="A1",
        valueInputOption="RAW", body={"values": [HEADERS]},
    ).execute()
    _save_sheet_id(sid)
    return sid


def append_row(date, person, company, role, notes):
    """Append one interview row; create the sheet first if it does not exist."""
    try:
        service = _service()
        sid = _ensure_sheet(service)
        service.spreadsheets().values().append(
            spreadsheetId=sid, range="A1",
            valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
            body={"values": [[date, person, company, role, notes]]},
        ).execute()
    except HttpError as e:
        raise SheetsError(f"Google Sheets API error: {e}") from e
    return {"spreadsheet_id": sid,
            "url": f"https://docs.google.com/spreadsheets/d/{sid}/edit"}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        get_credentials(interactive=True)
        print("Authorized. token.json written.")
    else:
        print("Usage: ./venv/bin/python sheets.py auth")
