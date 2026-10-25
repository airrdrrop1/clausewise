"""ClauseWise pipeline: extract (Nano) -> reason (Super) -> verify (code).

The verification stage is deliberately NOT an LLM call: every red-flag quote
returned by the reasoning stage is checked, in plain Python, against the
source contract text. Quotes that cannot be found are flagged
``verified: false`` so a fabricated clause can never be presented as real.
"""

import json
import re

from token_factory import TokenFactoryClient


class AnalysisError(ValueError):
    """Raised when the pipeline cannot produce a trustworthy brief —
    e.g. the model returned output that is not the JSON it was asked
    for. Subclasses ValueError so callers can catch input problems and
    analysis problems uniformly and show the message to the user."""

EXTRACT_SYSTEM = (
    "You extract structured facts from contracts. Reply with JSON only, "
    "no prose, no markdown fences. Schema: {\"parties\": [str], "
    "\"effective_date\": str|null, \"term\": str|null, "
    "\"payment\": {\"amount\": str|null, \"schedule\": str|null}, "
    "\"deliverables\": [str], \"deadlines\": [{\"what\": str, \"when\": str}], "
    "\"termination\": str|null, \"ip_ownership\": str|null, "
    "\"confidentiality\": str|null}. Use null instead of inventing values."
)

REASON_SYSTEM = (
    "You are a contract risk analyst for freelancers. Given contract text "
    "and extracted facts, reply with JSON only, no prose, no markdown "
    "fences. Schema: {\"summary\": str, \"red_flags\": [{\"title\": str, "
    "\"severity\": \"high\"|\"medium\"|\"low\", \"why\": str, "
    "\"quote\": str}], \"obligations\": [str], \"questions\": [str]}. "
    "Every red_flags[].quote MUST be copied verbatim from the contract "
    "text. Never paraphrase a quote."
)


def _parse_json(text, stage="model"):
    """Defensive JSON parse: strip fences, fall back to first {...} block.

    Raises AnalysisError with a user-presentable message when the model
    output cannot be parsed or is not a JSON object — the pipeline must
    fail loudly and gracefully, never fabricate a brief."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                parsed = None
    if not isinstance(parsed, dict):
        raise AnalysisError(
            f"The {stage} stage returned output that could not be parsed "
            "as JSON. Please try again."
        )
    return parsed


def _normalize(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def verify_quotes(red_flags, source_text):
    """Deterministically check each quote exists in the source text."""
    haystack = _normalize(source_text)
    for flag in red_flags:
        quote = _normalize(flag.get("quote", ""))
        flag["verified"] = bool(quote) and quote in haystack
    return red_flags


def analyze_contract(text, client=None):
    client = client or TokenFactoryClient()
    if not isinstance(text, str):
        raise ValueError("Contract text must be a string.")
    if len(text.strip()) < 50:
        raise ValueError("Contract text is too short to analyze.")

    extract_raw = client.chat(
        [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": text[:60000]},
        ],
        tier="nano",
    )
    facts = _parse_json(extract_raw["content"], stage="extraction")

    reason_raw = client.chat(
        [
            {"role": "system", "content": REASON_SYSTEM},
            {
                "role": "user",
                "content": (
                    "CONTRACT TEXT:\n" + text[:60000]
                    + "\n\nEXTRACTED FACTS:\n" + json.dumps(facts)
                ),
            },
        ],
        tier="super",
        max_tokens=6144,
    )
    brief = _parse_json(reason_raw["content"], stage="reasoning")

    raw_flags = brief.get("red_flags", [])
    if not isinstance(raw_flags, list):
        raw_flags = []
    red_flags = verify_quotes(
        [f for f in raw_flags if isinstance(f, dict)], text
    )
    obligations = brief.get("obligations", [])
    questions = brief.get("questions", [])
    return {
        "facts": facts,
        "summary": brief.get("summary", "") if isinstance(brief.get("summary", ""), str) else "",
        "red_flags": red_flags,
        "obligations": obligations if isinstance(obligations, list) else [],
        "questions": questions if isinstance(questions, list) else [],
        "mode": extract_raw["mode"],
        "models": {"extract": extract_raw["model"], "reason": reason_raw["model"]},
        "usage": {"extract": extract_raw["usage"], "reason": reason_raw["usage"]},
        "disclaimer": "ClauseWise is an educational reading aid, not legal advice.",
    }
