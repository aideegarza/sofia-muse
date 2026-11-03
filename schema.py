"""The 18 call fields Sofía's hackathon demo must produce, plus three enrichment fields.

This is the single source of truth: the JSON schema sent to Muse Spark, the
validation of its answer, and the column order of the Google Sheet all come
from FIELDS below.
"""

TRANSFER_TARGETS = ["case_support", "accounting", "intake", "daniela",
                    "ricardo", "camila", "hector", "valeria", "none"]

# (name, json type, description, enum choices or None)
FIELDS = [
    ("name", "string", "Caller's name as they said it. Empty string if never given.", None),
    ("language", "string", "Main language the caller used.", ["es", "en"]),
    ("immigration_call", "boolean", "True if the caller's matter is about U.S. immigration.", None),
    ("subagent", "string", "Path the call followed, judged from the conversation.",
     ["new", "client", "live", "reception", "pcinprocess", "others"]),
    ("initial_request", "string", "Why they called, in a short phrase in the caller's own terms.", None),
    ("source", "string", "Where a new or live caller found the firm: TikTok, Facebook, Instagram, YouTube, Referral, Other. Empty string if not discussed.", None),
    ("detention", "boolean", "True if someone is detained right now. False if not discussed.", None),
    ("detention_details", "string", "Detained person's name, detention center and when detained. Empty string if no detention.", None),
    ("contact_preference", "string", "How the caller wants to be contacted for the pre-evaluation.", ["asap", "scheduled", "none"]),
    ("appointment_date", "string", "Booked or preferred follow-up day and time including the timezone the caller was given, e.g. 'November 3 2026 10:30 AM Pacific'. Empty string if none.", None),
    ("email", "string", "Caller's email exactly as given. Empty string if not given.", None),
    ("message", "string", "Message the caller left for the team. Empty string if none.", None),
    ("caller_type", "string", "Who called, based on the route the call followed. incomplete = hung up or reason unknown.",
     ["client", "prospect_in_process", "new", "reception", "others", "incomplete"]),
    ("call_outcome", "string",
     "Final outcome. Client: payment, document_followup, detained, client_other. New: appointment_scheduled, call_asap, detained_new, new_other. Others: vendor, authority, non_immigration. not_applicable: reception or prospect_in_process. incomplete: hung up or reason unknown.",
     ["payment", "document_followup", "detained", "client_other", "appointment_scheduled", "call_asap",
      "detained_new", "new_other", "vendor", "authority", "non_immigration", "not_applicable", "incomplete"]),
    ("transferred", "boolean", "True only if the call was handed off to a person or area. False if a message was taken instead.", None),
    ("transfer_destination", "string", "Area or person the call was transferred, or attempted to be transferred, to. none if no transfer was attempted.", TRANSFER_TARGETS),
    ("after_hours", "boolean", "True if the office was closed during the call.", None),
    ("high_priority", "boolean", "True if someone is detained or the caller is police, ICE, a judge or another government authority.", None),
    # --- enrichment beyond the 18 required fields ---
    ("summary_es", "string", "Two-sentence summary of the call in Spanish for the team, no legal advice.", None),
    ("urgency", "string", "How urgent follow-up is: high = detention, authority, or a deadline in days; medium = wants a call soon; low = information only.", ["high", "medium", "low"]),
    ("next_action", "string", "One concrete next step for the team, in Spanish, e.g. 'Llamar mañana 10 AM para pre-evaluación'.", None),
]

REQUIRED_18 = [f[0] for f in FIELDS[:18]]


def json_schema() -> dict:
    props = {}
    for name, typ, desc, choices in FIELDS:
        p = {"type": typ, "description": desc}
        if choices:
            p["enum"] = choices
        props[name] = p
    return {
        "type": "object",
        "properties": props,
        "required": [f[0] for f in FIELDS],
        "additionalProperties": False,
    }


def validate(data: dict) -> list[str]:
    """Return a list of problems; empty means the answer matches the schema."""
    problems = []
    py_types = {"string": str, "boolean": bool}
    for name, typ, _, choices in FIELDS:
        if name not in data:
            problems.append(f"missing {name}")
            continue
        v = data[name]
        if not isinstance(v, py_types[typ]):
            problems.append(f"{name} should be {typ}, got {type(v).__name__}")
        elif choices and v not in choices:
            problems.append(f"{name}={v!r} not in {choices}")
    extra = set(data) - {f[0] for f in FIELDS}
    if extra:
        problems.append(f"unexpected fields {sorted(extra)}")
    return problems
