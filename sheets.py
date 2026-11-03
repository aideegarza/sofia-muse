"""Write one processed call as a row in Google Sheets through an Apps Script web app.

The Apps Script (apps_script.gs) upserts by call_id, so Retell's webhook retries
never create duplicate rows.
"""
import os

import requests

from schema import FIELDS

META_COLUMNS = ["call_id", "start_time_utc", "duration_seconds", "from_last4",
                "model", "latency_ms", "input_tokens", "output_tokens", "recording_url"]
COLUMNS = META_COLUMNS + [f[0] for f in FIELDS]


def to_row(result: dict) -> dict:
    meta = result.get("_meta", {})
    row = {c: meta.get(c) for c in META_COLUMNS}
    row.update({f[0]: result.get(f[0]) for f in FIELDS})
    return row


def save(result: dict) -> None:
    url = os.environ.get("SHEETS_WEBAPP_URL")
    if not url:
        print("[sheets] SHEETS_WEBAPP_URL not set; row not saved", flush=True)
        return
    payload = {"token": os.environ.get("SHEETS_TOKEN", ""), "columns": COLUMNS, "row": to_row(result)}
    r = requests.post(url, json=payload, timeout=30)
    if r.status_code != 200 or '"ok":true' not in r.text.replace(" ", ""):
        raise RuntimeError(f"Sheets web app answered {r.status_code}: {r.text[:300]}")
