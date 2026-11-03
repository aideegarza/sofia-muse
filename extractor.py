"""Send a finished Retell call to Muse Spark and get the 18 fields back as validated JSON.

Run it alone to test without Retell:
    MODEL_API_KEY=... python extractor.py tests/sample_call.json
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

from schema import json_schema, validate

MUSE_URL = os.environ.get("MUSE_BASE_URL", "https://api.meta.ai/v1") + "/chat/completions"
MUSE_MODEL = os.environ.get("MUSE_MODEL", "muse-spark-1.3")
REASONING_EFFORT = os.environ.get("MUSE_REASONING_EFFORT", "low")

SYSTEM_PROMPT = """You analyze finished phone calls handled by Sofía, the bilingual (Spanish/English) AI receptionist of a U.S. immigration law firm.
Read the transcript and the call metadata and fill every field of the schema.

Rules:
- Use only what is in the transcript and metadata. Never invent names, emails, dates or details.
- If something was not discussed, use an empty string, false, or the 'none'/'incomplete' choice the field offers.
- 'Agent' lines are Sofía; 'User' lines are the caller.
- A transfer happened only if Sofía said she was connecting the caller with the team AND the metadata or transcript shows the call was handed off. Taking a message is not a transfer.
- When metadata gives a deterministic value (office hours, transfer), trust it over your reading of the transcript.
- Write summary_es and next_action in Spanish, plainly, with no legal advice and no opinion on the case's chances.
"""


def _metadata(call: dict) -> dict:
    """Facts we know for certain from Retell, given to the model as hints."""
    start, end = call.get("start_timestamp"), call.get("end_timestamp")
    dyn = call.get("collected_dynamic_variables") or {}
    meta = {
        "call_id": call.get("call_id"),
        "start_time_utc": datetime.fromtimestamp(start / 1000, timezone.utc).isoformat() if start else None,
        "duration_seconds": round((end - start) / 1000) if start and end else None,
        "disconnection_reason": call.get("disconnection_reason"),
    }
    if dyn.get("office_hours") in ("si", "no"):
        meta["office_hours"] = dyn["office_hours"]
    if dyn.get("transfer_target"):
        meta["transfer_target_chosen_by_flow"] = dyn["transfer_target"]
    return meta


def _transcript(call: dict) -> str:
    if call.get("transcript"):
        return call["transcript"]
    turns = call.get("transcript_object") or []
    return "\n".join(f"{t.get('role', '').capitalize()}: {t.get('content', '')}" for t in turns)


def _post_with_retry(payload: dict, api_key: str, attempts: int = 4) -> dict:
    for i in range(attempts):
        r = requests.post(MUSE_URL, json=payload, timeout=120,
                          headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504) and i < attempts - 1:
            time.sleep(2 ** i + random.random())
            continue
        raise RuntimeError(f"Muse Spark returned HTTP {r.status_code}: {r.text[:500]}")
    raise RuntimeError("Muse Spark: retries exhausted")


def _apply_deterministic(data: dict, call: dict) -> dict:
    """Facts Retell knows for sure win over the model's reading."""
    dyn = call.get("collected_dynamic_variables") or {}
    if dyn.get("office_hours") in ("si", "no"):
        data["after_hours"] = dyn["office_hours"] == "no"
    if call.get("disconnection_reason") == "call_transfer":
        data["transferred"] = True
    if data.get("detention") or data.get("call_outcome") == "authority":
        data["high_priority"] = True
    return data


def extract(call: dict, api_key: str | None = None) -> dict:
    api_key = api_key or os.environ["MODEL_API_KEY"]
    transcript = _transcript(call)
    if not transcript.strip():
        raise ValueError("call has no transcript")

    user_msg = ("CALL METADATA (deterministic):\n" + json.dumps(_metadata(call), ensure_ascii=False, indent=2)
                + "\n\nTRANSCRIPT:\n" + transcript)
    payload = {
        "model": MUSE_MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "messages": [
            {"role": "developer", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "sofia_call", "schema": json_schema()}},
    }

    started = time.time()
    resp = _post_with_retry(payload, api_key)
    data = json.loads(resp["choices"][0]["message"]["content"])
    problems = validate(data)
    if problems:
        raise ValueError(f"Muse Spark answer failed validation: {problems}")
    data = _apply_deterministic(data, call)

    usage = resp.get("usage") or {}
    data["_meta"] = {
        "call_id": call.get("call_id"),
        "model": resp.get("model", MUSE_MODEL),
        "latency_ms": round((time.time() - started) * 1000),
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        **{k: v for k, v in _metadata(call).items() if k in ("start_time_utc", "duration_seconds")},
        "recording_url": call.get("recording_url"),
        "from_last4": (call.get("from_number") or "")[-4:],
    }
    return data


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "tests/sample_call.json"
    body = json.load(open(path, encoding="utf-8"))
    call = body.get("call", body)
    print(json.dumps(extract(call), ensure_ascii=False, indent=2))
