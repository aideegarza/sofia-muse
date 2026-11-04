# Sofía × Muse Spark: call intelligence for immigration law firms

Sofía is a bilingual (Spanish/English) AI voice receptionist for U.S. immigration law firms. She answers 24/7, routes callers, books free pre-evaluations and transfers urgent calls to the team.

This repository holds the part that runs after every call. When a call ends, the server sends the transcript to **Muse Spark** through the Meta Model API. Muse Spark returns 18 structured fields, a summary in Spanish, an urgency level and a next action for the team. Each call becomes one row in Google Sheets.

```
Retell (voice)  ──call_ended webhook──▶  Server (Render)  ──transcript + JSON schema──▶  Muse Spark 1.3
                                               │                                            │
                                               ◀──────── validated JSON (18 + 3 fields) ─────┘
                                               │
                                               └──▶  Google Sheets (one row per call)
```

## How Muse Spark is used

- **Structured output.** The JSON schema in `schema.py` forces every answer to contain all 18 fields, with the right types and only the allowed values (enums). The server validates the answer before saving it.
- **Deterministic facts win.** Facts Retell knows for certain, such as office hours from the flow's HORARIO node and whether a transfer happened, override the model's reading of the transcript.
- **Priority rules.** Detention outranks every other outcome. Callers who mention a live show are tagged as `live`. Relative dates ("tomorrow", "next Tuesday") are resolved against the call's start time in U.S. Central Time.
- **Bilingual by design.** Calls can be in Spanish, English or a mix. Summaries and next actions are written in Spanish for the team.

## The 18 fields

`name`, `language`, `immigration_call`, `subagent`, `initial_request`, `source`, `detention`, `detention_details`, `contact_preference`, `appointment_date`, `email`, `message`, `caller_type`, `call_outcome`, `transferred`, `transfer_destination`, `after_hours`, `high_priority`

Enrichment fields: `summary_es`, `urgency`, `next_action`. Each row also stores the call ID, duration, the last four digits of the caller's number, model latency, token usage and a link to the recording.

## Files

| File | Purpose |
|---|---|
| `schema.py` | The 18 fields plus 3 enrichment fields. Single source of truth for the schema, the validation and the sheet columns |
| `extractor.py` | Muse Spark call with retries, validation and deterministic overrides |
| `app.py` | Server: `/retell` (webhook), `/test` (manual test), `/health` |
| `sheets.py` + `apps_script.gs` | Google Sheets writer, with no duplicate rows (upsert by `call_id`) |
| `render.yaml` | Render deployment configuration |
| `tests/` | Offline tests (Muse Spark and Sheets mocked) and a sample call |

## Environment variables

| Variable | Value |
|---|---|
| `MODEL_API_KEY` | Meta Model API key |
| `RETELL_API_KEY` | The Retell API key marked *webhook*, used to verify that each webhook comes from Retell |
| `SHEETS_WEBAPP_URL` | URL of the deployed Apps Script web app |
| `SHEETS_TOKEN` | Shared secret; must match `TOKEN` in the Apps Script |
| `TEST_TOKEN` | Secret required by the `/test` endpoint |
| `MUSE_MODEL` | `muse-spark-1.3` (default) |
| `MUSE_REASONING_EFFORT` | `low` (default); use `medium` for more accuracy at the cost of latency |

## Running the tests

```
pip install -r requirements.txt pytest
python -m pytest -q
```

## Privacy

All names, firms, phone numbers and emails in this repository and in the demo are fictional. Calls are processed with the Meta Model API in Standard mode, not Contributor mode, so call content is not used for model training.

Built during the Meta Global AI Developer Hackathon (November 2026).
