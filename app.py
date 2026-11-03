"""Webhook server: Retell -> Muse Spark -> Google Sheets.

Endpoints
  GET  /health        -> "ok" (Render uses it to check the service is up)
  POST /retell        -> Retell webhook. Answers 204 at once, processes call_ended in the background.
  POST /test          -> Process a call JSON you send, wait for the result and return it.
                         Needs header X-Test-Token = TEST_TOKEN. Handy before Retell is wired.
"""
import json
import os
import threading
import traceback

from flask import Flask, Response, jsonify, request

import extractor
import sheets

app = Flask(__name__)
_seen: set[str] = set()          # call_ids already queued (Retell may retry)
_lock = threading.Lock()


def _verify_retell(raw_body: str, signature: str | None) -> bool:
    key = os.environ.get("RETELL_API_KEY")
    if not key:
        return os.environ.get("ALLOW_UNSIGNED") == "true"
    if not signature:
        return False
    from retell import Retell  # imported here so local tests don't need the SDK
    return Retell(api_key=key).verify(raw_body, api_key=key, signature=signature)


def _process(call: dict) -> None:
    call_id = call.get("call_id")
    try:
        result = extractor.extract(call)
        sheets.save(result)
        print(f"[ok] {call_id} outcome={result['call_outcome']} urgency={result['urgency']} "
              f"latency={result['_meta']['latency_ms']}ms", flush=True)
    except Exception:
        with _lock:
            _seen.discard(call_id)   # let a Retell retry try again
        print(f"[error] {call_id}\n{traceback.format_exc()}", flush=True)


@app.get("/health")
def health():
    return "ok"


@app.post("/retell")
def retell_webhook():
    raw = request.get_data(as_text=True)
    if not _verify_retell(raw, request.headers.get("X-Retell-Signature")):
        return Response(status=401)

    body = json.loads(raw)
    if body.get("event") != "call_ended":
        return Response(status=204)

    call = body.get("call") or {}
    call_id = call.get("call_id")
    with _lock:
        if call_id in _seen:
            return Response(status=204)
        _seen.add(call_id)
    threading.Thread(target=_process, args=(call,), daemon=True).start()
    return Response(status=204)


@app.post("/test")
def test_endpoint():
    token = os.environ.get("TEST_TOKEN")
    if not token or request.headers.get("X-Test-Token") != token:
        return Response(status=401)
    body = request.get_json(force=True)
    call = body.get("call", body)
    result = extractor.extract(call)
    if request.args.get("save") == "1":
        sheets.save(result)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
