"""Nebius Token Factory client (OpenAI-compatible), stdlib only.

Two-tier router for NVIDIA Nemotron models:
  tier="nano"  -> fast/cheap calls (structured extraction)
  tier="super" -> heavy reasoning calls (risk analysis)

If NEBIUS_API_KEY is not set, the client runs in MOCK mode: it returns
clearly-marked placeholder content so the whole app works offline and the
repository can be tested by anyone. Mock output is never presented as a
real model result — callers surface `mode` in the UI.
"""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path


def _load_dotenv():
    """Minimal .env support (stdlib only): read KEY=VALUE lines from a
    .env file next to this module into os.environ, without overriding
    variables that are already set. Missing file is fine."""
    env_file = Path(__file__).with_name(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()

BASE_URL = os.environ.get(
    "TOKEN_FACTORY_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"
).rstrip("/") + "/"

MODELS = {
    "nano": os.environ.get("MODEL_NANO", "nvidia/nemotron-3-nano-30b-a3b"),
    "super": os.environ.get("MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b"),
}


class TokenFactoryError(Exception):
    pass


# Canned demo output for mock mode, derived from the bundled sample
# contract (samples/freelance-contract-sample.txt). Every quote below is
# verbatim from that sample, so loading the sample in the UI makes the
# verification layer pass end-to-end; pasting other text in mock mode
# will (correctly) flag these quotes as unverified — the checker is real
# even when the "model" is canned. The UI labels mock mode prominently.
_MOCK_EXTRACT = {
    "parties": ["BrightNest Studio Ltd.", "A. Freelancer"],
    "effective_date": "1 March 2026",
    "term": "12 months, auto-renewing",
    "payment": {"amount": "USD 2,400", "schedule": "within 60 days"},
    "deliverables": ["logo suite", "brand guideline document"],
    "deadlines": [{"what": "final files", "when": "15 April 2026"}],
    "termination": "Client may terminate at any time without fee",
    "ip_ownership": "Client, upon creation",
    "confidentiality": "5 years after termination",
}

_MOCK_REASON = {
    "summary": (
        "Demo analysis of the bundled sample contract: a one-sided "
        "freelance design agreement. The client can deduct fees, take "
        "ownership of all work before paying, and walk away at any time, "
        "while the designer's liability is unlimited."
    ),
    "red_flags": [
        {
            "title": "Client can deduct 5% from any invoice at will",
            "severity": "high",
            "why": "A unilateral 'administration charge' means the agreed fee is not actually guaranteed.",
            "quote": "Client may deduct a 5% \"administration charge\" from any invoice at its sole discretion",
        },
        {
            "title": "IP transfers before payment",
            "severity": "high",
            "why": "Ownership of all work — including drafts and rejected concepts — passes on creation, while payment is net-60.",
            "quote": "becomes the exclusive property of Client upon creation",
        },
        {
            "title": "Client can terminate instantly, designer cannot",
            "severity": "medium",
            "why": "The client may exit at any time with no fee; the designer may only terminate for material breach with 60 days' notice.",
            "quote": "terminate this Agreement at any time, for any reason, with immediate effect and without any termination fee",
        },
        {
            "title": "Unlimited liability for the designer",
            "severity": "high",
            "why": "The designer's liability is uncapped while the client's is limited to fees paid — a heavily one-sided risk split.",
            "quote": "Designer's total liability under this Agreement shall be unlimited",
        },
    ],
    "obligations": [
        "Deliver final files by 15 April 2026 (time is of the essence)",
        "Provide unlimited revisions at no additional charge",
        "Keep all Client materials confidential for 5 years after termination",
    ],
    "questions": [
        "Is the 5% administration deduction negotiable or removable?",
        "Can IP transfer be tied to full payment instead of creation?",
        "Can a kill fee be added if the client terminates early?",
    ],
}


class TokenFactoryClient:
    def __init__(self, api_key=None):
        self.api_key = api_key if api_key is not None else os.environ.get("NEBIUS_API_KEY", "")
        self.mode = "live" if self.api_key else "mock"

    def chat(self, messages, tier="nano", max_tokens=4096, temperature=0.2):
        """Return {'content': str, 'model': str, 'usage': dict|None, 'mode': str}."""
        model = MODELS[tier]
        if self.mode == "mock":
            payload = _MOCK_EXTRACT if tier == "nano" else _MOCK_REASON
            return {
                "content": json.dumps(payload),
                "model": model + " (mock)",
                "usage": None,
                "mode": "mock",
            }
        body = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")
        req = urllib.request.Request(
            BASE_URL + "chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise TokenFactoryError(f"Token Factory HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise TokenFactoryError(f"Token Factory unreachable: {e.reason}") from e

        msg = data["choices"][0]["message"]
        # Nemotron models are reasoning models: when `content` is empty the
        # answer may live in `reasoning_content`.
        content = msg.get("content") or msg.get("reasoning_content") or ""
        return {
            "content": content,
            "model": data.get("model", model),
            "usage": data.get("usage"),
            "mode": "live",
        }

    def list_models(self):
        """GET /v1/models — use once after key setup to confirm model IDs."""
        req = urllib.request.Request(
            BASE_URL + "models",
            headers={"Authorization": "Bearer " + self.api_key},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
