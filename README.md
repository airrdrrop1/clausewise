# ClauseWise — Know what you sign

Freelancers and small businesses sign client contracts and terms they do
not fully understand: net-60 payment with a unilateral fee deduction, IP
that transfers before a cent is paid, one-sided termination, unlimited
liability. A lawyer is too expensive for a $2,400 contract — and a plain
LLM summary is not the answer either, because it can quote clauses that
do not exist with total confidence.

**ClauseWise turns a contract into a plain-language brief whose warnings
you can check.** Paste the contract text and you get:

- a three-sentence summary in plain language,
- a structured fact card — parties, money, deadlines, termination, IP,
  confidentiality,
- a list of **red flags**, each with a severity, an explanation, and the
  *exact clause quoted verbatim*,
- your obligations and deadlines, and questions worth asking before you
  sign.

The differentiator is the last pipeline stage: **every quote is verified
by deterministic code against your text.** A warning whose quote cannot
be found is visibly flagged as unverified instead of being presented as
fact. The brief cannot invent contract language — and when a model tries,
ClauseWise catches it.

> ClauseWise is an educational reading aid, not legal advice.

Built for the **Nebius x NVIDIA Global AI Hackathon**, track
*Best Apps and Agents*. All inference runs at runtime on
**Nebius Token Factory** with **NVIDIA Nemotron** open models.

## Architecture: a three-stage pipeline that verifies itself

```
Browser ──► app.py  (Python stdlib http.server — zero dependencies)
              │
              └─► analyze.py — pipeline
                    1. EXTRACT   Nemotron 3 Nano   → structured facts (JSON)
                    2. REASON    Nemotron 3 Super  → summary + red flags,
                                                     each with a verbatim quote
                    3. VERIFY    plain Python      → every quote checked
                                                     against the source text
              token_factory.py — OpenAI-compatible client for
              https://api.tokenfactory.nebius.com/v1/ (Bearer auth)
```

### Why these two models

- **Nemotron 3 Nano (30B)** for extraction: the task is fast, structured
  and repeated — pull fields into a fixed JSON schema. Nano is the cheap,
  low-latency tier, and using a small model where a small model suffices
  keeps a full analysis far below $0.05.
- **Nemotron 3 Super (120B)** for risk reasoning: judging whether a clause
  is one-sided requires weighing clauses against each other (IP transfer
  *timing* vs. payment *schedule*), which is exactly the deep-reasoning
  pass Super is for.
- **No model at all** for verification: quote checking is substring
  matching after whitespace/case normalization. Deterministic code is
  the whole point — an LLM "checking itself" would defeat the purpose.

Nemotron models are reasoning models, so the client reads
`reasoning_content` when `content` is empty. Structured output is
requested as JSON in the prompt and parsed defensively (fence stripping,
object extraction, hard failure with a clear error if parsing fails —
never a fabricated fallback brief).

## Run it locally

Requirements: Python 3.10+ — **standard library only, nothing to install.**

```bash
cp .env.example .env     # then put your key in .env (see below)
python3 app.py           # http://localhost:8080  (PORT env var overrides)
```

Open the page, paste a contract (or click *Load the sample contract* —
a fictional freelance agreement with several planted one-sided clauses),
and press **Analyze contract**.

### Mock mode (no key needed)

Without `NEBIUS_API_KEY` the app runs in **offline demo mode**, labelled
by a prominent banner in the UI and by `mode: "mock"` in every API
response. The canned result is derived from the bundled sample contract,
so loading the sample shows every quote verifying end-to-end. Paste a
different text and the sample quotes are correctly flagged as
*unverified* — the verification layer is real code, not part of the mock.

### Live mode (Nebius Token Factory)

1. Create a Token Factory API key in the Nebius console.
2. Confirm the exact model IDs available to your account:
   `GET https://api.tokenfactory.nebius.com/v1/models` with
   `Authorization: Bearer <your key>`. Defaults in `.env.example` are
   `nvidia/nemotron-3-nano-30b-a3b` and `nvidia/nemotron-3-super-120b-a12b`;
   override with `MODEL_NANO` / `MODEL_SUPER` if your account differs.
3. Put the key in `.env` as `NEBIUS_API_KEY=...` (the app loads `.env`
   itself; a real environment variable takes precedence). **Never commit
   a real key** — `.env` is git-ignored.
4. Restart `app.py`. The UI banner switches to LIVE MODE and each result
   shows the models used and per-stage token usage.

## Tests

The test suite uses fake clients and localhost only — no key, no network.

```bash
python3 tests/test_pipeline.py   # pipeline: extraction, verification, errors
python3 tests/test_app.py        # HTTP smoke tests for the demo server
# both files are also pytest-compatible:  python3 -m pytest tests/ -q
```

Covered cases include: a fabricated quote being caught by verification;
a quote altered by a single word or digit failing verification; a clean
contract producing zero red flags; empty, non-string, and too-short
input rejected gracefully; unparseable model output raising a clear
error instead of a fake brief; and mock mode running end-to-end.

## Project layout

```
app.py            web server + one-page UI (stdlib only)
analyze.py        the 3-stage pipeline (extract → reason → verify)
token_factory.py  Token Factory client, two-tier model router, mock mode
samples/          fictional sample contract used by the demo and tests
tests/            pipeline + HTTP tests (fake clients, no network)
.env.example      configuration template (never commit a real .env)
LICENSE           MIT
```

## Honest limitations

- **Verification is conservative, not semantic.** Quotes are matched
  after whitespace and case normalization only. A quote that differs by
  punctuation or a single word is reported *unverified* even if the
  meaning is identical — ClauseWise prefers a false alarm over a false
  "verified".
- **It reads text, not files.** Paste the contract text; there is no
  PDF/DOCX upload, and input is truncated at 60,000 characters per call.
- **Quality depends on the model output.** Extraction asks for `null`
  instead of guesses, but a missed clause is possible; the fact card is
  a reading aid, not a guarantee of completeness.
- **Not legal advice.** ClauseWise explains contracts in plain language
  for educational purposes. For anything that matters, consult a lawyer.

## License

MIT — see `LICENSE`.
