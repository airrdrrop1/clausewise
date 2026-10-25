"""Pipeline tests with a fake Token Factory client (no network, no key).

Key case: the reasoning stage fabricates one quote. The deterministic
verification layer must mark that flag verified=False while the real
quote passes.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyze import AnalysisError, analyze_contract, verify_quotes
from token_factory import TokenFactoryClient

SAMPLE = (Path(__file__).parent.parent / "samples" / "freelance-contract-sample.txt").read_text()


class FakeClient:
    mode = "live"

    def chat(self, messages, tier="nano", **kw):
        if tier == "nano":
            content = {
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
        else:
            content = {
                "summary": "One-sided sample contract.",
                "red_flags": [
                    {
                        "title": "IP transfers before payment",
                        "severity": "high",
                        "why": "Ownership passes on creation, payment is net-60.",
                        "quote": "becomes the exclusive property of Client upon creation",
                    },
                    {
                        "title": "Fabricated clause (test)",
                        "severity": "high",
                        "why": "This quote does not exist in the contract.",
                        "quote": "Designer must pay Client a penalty of USD 9,999 per day",
                    },
                ],
                "obligations": ["Deliver final files by 15 April 2026"],
                "questions": ["Is the 5% administration deduction negotiable?"],
            }
        return {"content": json.dumps(content), "model": f"fake-{tier}", "usage": None, "mode": "live"}


def test_pipeline_end_to_end():
    result = analyze_contract(SAMPLE, client=FakeClient())
    assert result["facts"]["payment"]["amount"] == "USD 2,400"
    assert len(result["red_flags"]) == 2


def test_verification_catches_fabrication():
    result = analyze_contract(SAMPLE, client=FakeClient())
    by_title = {f["title"]: f for f in result["red_flags"]}
    assert by_title["IP transfers before payment"]["verified"] is True
    assert by_title["Fabricated clause (test)"]["verified"] is False


def test_verify_quotes_normalizes_whitespace():
    flags = [{"quote": "renews automatically for  successive twelve-month periods"}]
    verify_quotes(flags, SAMPLE)
    assert flags[0]["verified"] is True


class CleanClient:
    """A fair, balanced contract: the reasoning stage finds nothing."""

    mode = "live"

    def chat(self, messages, tier="nano", **kw):
        if tier == "nano":
            content = {
                "parties": ["Client Co", "Freelancer"],
                "effective_date": "1 May 2026",
                "term": "6 months",
                "payment": {"amount": "USD 1,000", "schedule": "within 14 days"},
                "deliverables": ["website"],
                "deadlines": [],
                "termination": "Either party, 30 days' notice",
                "ip_ownership": "Client, upon full payment",
                "confidentiality": "Mutual, 2 years",
            }
        else:
            content = {
                "summary": "Balanced short agreement; no one-sided clauses found.",
                "red_flags": [],
                "obligations": ["Deliver the website by the agreed date"],
                "questions": [],
            }
        return {"content": json.dumps(content), "model": f"fake-{tier}", "usage": None, "mode": "live"}


CLEAN_CONTRACT = (
    "Services Agreement between Client Co and Freelancer, effective "
    "1 May 2026. Fee USD 1,000 payable within 14 days of invoice. "
    "Intellectual property transfers to Client upon full payment. "
    "Either party may terminate with thirty (30) days' written notice."
)


def test_clean_contract_has_no_red_flags():
    result = analyze_contract(CLEAN_CONTRACT, client=CleanClient())
    assert result["red_flags"] == []
    assert result["summary"]
    assert result["facts"]["ip_ownership"] == "Client, upon full payment"


def _assert_raises(exc_type, fn, *args, **kw):
    try:
        fn(*args, **kw)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__} from {fn.__name__}")


def test_empty_and_garbage_input_rejected_gracefully():
    for bad in ("", "   \n\t ", "too short", None, 12345, ["not", "a", "string"]):
        _assert_raises(ValueError, analyze_contract, bad, CleanClient())


class GarbageClient:
    """Returns prose instead of JSON — the pipeline must fail gracefully."""

    mode = "live"

    def chat(self, messages, tier="nano", **kw):
        return {
            "content": "Sure! Here is my analysis of the contract... (no JSON)",
            "model": f"fake-{tier}",
            "usage": None,
            "mode": "live",
        }


def test_unparseable_model_output_raises_analysis_error():
    _assert_raises(AnalysisError, analyze_contract, SAMPLE, GarbageClient())


def test_slightly_modified_quote_fails_verification():
    # Exact quote and a case-only variant pass (normalization covers
    # whitespace and case)...
    flags = [
        {"quote": "becomes the exclusive property of Client upon creation"},
        {"quote": "BECOMES THE EXCLUSIVE PROPERTY OF CLIENT UPON CREATION"},
        # ...but one inserted word or one changed number must fail.
        {"quote": "becomes the exclusive property of the Client upon creation"},
        {"quote": "gives notice ninety (91) days before renewal"},
    ]
    verify_quotes(flags, SAMPLE)
    assert flags[0]["verified"] is True
    assert flags[1]["verified"] is True
    assert flags[2]["verified"] is False
    assert flags[3]["verified"] is False


def test_mock_mode_end_to_end():
    # No API key -> the real client runs in mock mode. On the bundled
    # sample, every canned quote must verify; on unrelated text the
    # same quotes must (correctly) fail verification.
    client = TokenFactoryClient(api_key="")
    assert client.mode == "mock"
    result = analyze_contract(SAMPLE, client=client)
    assert result["mode"] == "mock"
    assert len(result["red_flags"]) >= 3
    assert all(f["verified"] for f in result["red_flags"])

    unrelated = (
        "Consulting agreement between Alpha LLC and Beta Studio for "
        "marketing services over six months, invoiced monthly, with "
        "standard confidentiality terms and delivery by email."
    )
    other = analyze_contract(unrelated, client=client)
    assert other["mode"] == "mock"
    assert not any(f["verified"] for f in other["red_flags"])


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"all {len(tests)} tests passed")
