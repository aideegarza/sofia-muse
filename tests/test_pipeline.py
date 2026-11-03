"""Offline tests: Muse Spark and Google Sheets are mocked, so no keys are needed.

Run: python -m pytest -q
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as server  # noqa: E402
import extractor  # noqa: E402
import sheets  # noqa: E402
from schema import FIELDS, REQUIRED_18, json_schema, validate  # noqa: E402

SAMPLE = json.loads((ROOT / "tests" / "sample_call.json").read_text(encoding="utf-8"))

GOOD_ANSWER = {
    "name": "Mariana López", "language": "es", "immigration_call": True, "subagent": "live",
    "initial_request": "su esposo fue detenido por ICE", "source": "TikTok", "detention": True,
    "detention_details": "Jorge Ramírez Torres, Prairieland, detenido ayer en la mañana",
    "contact_preference": "scheduled", "appointment_date": "Tuesday 9:00 AM Central",
    "email": "mariana.lopez@example.com", "message": "", "caller_type": "new",
    "call_outcome": "detained_new", "transferred": False, "transfer_destination": "none",
    "after_hours": False,  # deliberately wrong: office_hours metadata must override it
    "high_priority": False,  # deliberately wrong: detention must force it to True
    "summary_es": "Esposa de persona detenida por ICE. Se agendó pre-evaluación.",
    "urgency": "high", "next_action": "Llamar mañana 9:00 AM para pre-evaluación de emergencia",
}


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


def muse_ok(answer):
    return FakeResp(200, {"model": "muse-spark-1.3",
                          "choices": [{"message": {"content": json.dumps(answer)}}],
                          "usage": {"prompt_tokens": 1500, "completion_tokens": 300}})


def test_schema_has_the_18_required_fields():
    assert len(REQUIRED_18) == 18
    s = json_schema()
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {f[0] for f in FIELDS}


def test_extract_sends_schema_and_applies_deterministic_overrides(monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, payload=json, headers=headers)
        return muse_ok(GOOD_ANSWER)

    monkeypatch.setattr(extractor.requests, "post", fake_post)
    out = extractor.extract(SAMPLE["call"], api_key="k")

    assert sent["url"].endswith("/chat/completions")
    assert sent["headers"]["Authorization"] == "Bearer k"
    p = sent["payload"]
    assert p["model"] == "muse-spark-1.3"
    assert p["response_format"]["type"] == "json_schema"
    assert "Prairieland" in p["messages"][1]["content"]
    assert '"office_hours": "no"' in p["messages"][1]["content"]

    assert out["after_hours"] is True        # from office_hours = "no"
    assert out["high_priority"] is True      # forced by detention
    assert out["_meta"]["from_last4"] == "0188"
    assert out["_meta"]["duration_seconds"] == 312
    assert validate({k: v for k, v in out.items() if k != "_meta"}) == []


def test_extract_rejects_invalid_answer(monkeypatch):
    bad = dict(GOOD_ANSWER, call_outcome="maybe")
    monkeypatch.setattr(extractor.requests, "post", lambda *a, **k: muse_ok(bad))
    try:
        extractor.extract(SAMPLE["call"], api_key="k")
        assert False, "should have raised"
    except ValueError as e:
        assert "call_outcome" in str(e)


def test_extract_retries_on_429(monkeypatch):
    calls = iter([FakeResp(429, {"error": "rate"}), muse_ok(GOOD_ANSWER)])
    monkeypatch.setattr(extractor.requests, "post", lambda *a, **k: next(calls))
    monkeypatch.setattr(extractor.time, "sleep", lambda s: None)
    assert extractor.extract(SAMPLE["call"], api_key="k")["call_outcome"] == "detained_new"


def test_sheet_row_has_all_columns():
    row = sheets.to_row(dict(GOOD_ANSWER, _meta={"call_id": "x", "latency_ms": 10}))
    assert list(row) == sheets.COLUMNS
    assert row["call_id"] == "x" and row["email"] == "mariana.lopez@example.com"


def test_webhook_flow_end_to_end(monkeypatch):
    os.environ.pop("RETELL_API_KEY", None)
    os.environ["ALLOW_UNSIGNED"] = "true"
    saved = []
    monkeypatch.setattr(extractor.requests, "post", lambda *a, **k: muse_ok(GOOD_ANSWER))
    monkeypatch.setattr(sheets, "save", lambda r: saved.append(r))
    monkeypatch.setenv("MODEL_API_KEY", "k")
    server._seen.clear()
    client = server.app.test_client()

    # ignored events
    assert client.post("/retell", json={"event": "call_started", "call": {}}).status_code == 204
    # real event + a duplicate retry
    assert client.post("/retell", data=json.dumps(SAMPLE)).status_code == 204
    assert client.post("/retell", data=json.dumps(SAMPLE)).status_code == 204
    for _ in range(50):
        if saved:
            break
        time.sleep(0.05)
    time.sleep(0.1)
    assert len(saved) == 1
    assert saved[0]["call_outcome"] == "detained_new"


def test_webhook_rejects_unsigned_when_key_set(monkeypatch):
    monkeypatch.setenv("RETELL_API_KEY", "secret")
    client = server.app.test_client()
    assert client.post("/retell", data=json.dumps(SAMPLE)).status_code == 401


def test_test_endpoint_needs_token(monkeypatch):
    monkeypatch.setenv("TEST_TOKEN", "t")
    monkeypatch.setattr(extractor.requests, "post", lambda *a, **k: muse_ok(GOOD_ANSWER))
    monkeypatch.setenv("MODEL_API_KEY", "k")
    client = server.app.test_client()
    assert client.post("/test", json=SAMPLE).status_code == 401
    r = client.post("/test", json=SAMPLE, headers={"X-Test-Token": "t"})
    assert r.status_code == 200 and r.get_json()["urgency"] == "high"


def test_detention_outranks_appointment(monkeypatch):
    ans = dict(GOOD_ANSWER, call_outcome="appointment_scheduled", subagent="live")
    monkeypatch.setattr(extractor.requests, "post", lambda *a, **k: muse_ok(ans))
    out = extractor.extract(SAMPLE["call"], api_key="k")
    assert out["call_outcome"] == "detained_new"
    client_ans = dict(GOOD_ANSWER, caller_type="client", call_outcome="client_other")
    monkeypatch.setattr(extractor.requests, "post", lambda *a, **k: muse_ok(client_ans))
    assert extractor.extract(SAMPLE["call"], api_key="k")["call_outcome"] == "detained"
