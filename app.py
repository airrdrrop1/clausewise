"""ClauseWise web app — Python standard library only.

GET  /              -> one-page UI (paste contract, view brief)
GET  /api/status    -> {"mode": "mock"|"live", "models": {...}}
GET  /api/sample    -> bundled sample contract text
POST /api/analyze   -> {"text": "..."} -> analysis JSON (see analyze.py)

The analysis calls Nebius Token Factory at runtime with NVIDIA Nemotron
models. Without NEBIUS_API_KEY the pipeline runs in a clearly labelled
offline demo (mock) mode: the canned result is derived from the bundled
sample contract, while the quote-verification layer still runs for real
against whatever text was pasted.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from analyze import analyze_contract
from token_factory import MODELS, TokenFactoryClient

SAMPLE = Path(__file__).parent / "samples" / "freelance-contract-sample.txt"

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClauseWise — Know what you sign</title>
<style>
:root{--ink:#1a1a2e;--muted:#666;--line:#ddd;--high:#c0392b;--med:#e67e22;--low:#7f8c8d;--ok:#1e8449;--warn:#b7950b}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;max-width:860px;margin:0 auto;padding:1.5rem 1rem 3rem;color:var(--ink);line-height:1.5}
h1{margin-bottom:.2rem} h2{margin-top:1.8rem;border-bottom:2px solid var(--line);padding-bottom:.3rem}
.tagline{color:var(--muted);margin-top:0}
textarea{width:100%;height:230px;padding:.7rem;font:inherit;border:1px solid #bbb;border-radius:8px}
button{padding:.6rem 1.2rem;font-size:1rem;border:0;border-radius:8px;background:var(--ink);color:#fff;cursor:pointer}
button.secondary{background:#fff;color:var(--ink);border:1px solid #bbb}
button:disabled{opacity:.55;cursor:wait}
.banner{border-radius:8px;padding:.8rem 1rem;margin:1rem 0;font-size:.95rem}
.banner.mock{background:#fef9e7;border:2px solid var(--warn)}
.banner.live{background:#eafaf1;border:2px solid var(--ok)}
.meta{color:var(--muted);font-size:.85rem}
.flag{border:1px solid var(--line);border-left:6px solid var(--low);border-radius:8px;padding:.7rem .9rem;margin:.7rem 0;background:#fff}
.flag.high{border-left-color:var(--high)} .flag.medium{border-left-color:var(--med)} .flag.low{border-left-color:var(--low)}
.flag blockquote{margin:.5rem 0;padding:.5rem .8rem;background:#f7f7f7;border-left:3px solid #bbb;font-style:italic}
.pill{display:inline-block;padding:.05rem .55rem;border-radius:999px;font-size:.75rem;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:.04em}
.pill.high{background:var(--high)} .pill.medium{background:var(--med)} .pill.low{background:var(--low)}
.badge{display:inline-block;padding:.05rem .55rem;border-radius:999px;font-size:.78rem;font-weight:600}
.badge.ok{background:#eafaf1;color:var(--ok);border:1px solid var(--ok)}
.badge.bad{background:#fdedec;color:var(--high);border:1px solid var(--high)}
table{border-collapse:collapse;width:100%} td,th{border:1px solid var(--line);padding:.45rem .6rem;text-align:left;vertical-align:top}
th{background:#f7f7f7;width:32%}
.error{background:#fdedec;border:1px solid var(--high);border-radius:8px;padding:.8rem 1rem}
footer{margin-top:2.5rem;color:var(--muted);font-size:.9rem}
</style></head><body>
<h1>ClauseWise</h1>
<p class="tagline"><b>Know what you sign.</b> Paste a contract and get a plain-language brief:
structured facts, your obligations and deadlines, and red flags — every warning quotes the
exact clause it came from, and each quote is machine-checked against your text before it is
shown as verified.</p>

<div id="status"></div>

<p>
  <button type="button" class="secondary" onclick="loadSample()">Load the sample contract</button>
  <span class="meta">A fictional freelance agreement with several one-sided clauses — good for a first run.</span>
</p>
<textarea id="text" placeholder="Paste contract text here..."></textarea>
<p class="meta"><span id="count">0</span> characters</p>
<p><button id="go" onclick="run()">Analyze contract</button></p>

<div id="out"></div>

<footer>
<p>ClauseWise is an educational reading aid, <b>not legal advice</b>. For a contract that
matters, have a qualified lawyer review it.</p>
<p class="meta">Powered by NVIDIA Nemotron models on Nebius Token Factory
(Nemotron 3 Nano for extraction, Nemotron 3 Super for risk reasoning),
plus a deterministic quote-verification layer.</p>
</footer>

<script>
const $ = id => document.getElementById(id);
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

async function loadStatus(){
  try{
    const d = await (await fetch('/api/status')).json();
    if(d.mode === 'mock'){
      $('status').innerHTML = '<div class="banner mock"><b>OFFLINE DEMO MODE</b> — ' +
        'no NEBIUS_API_KEY is configured, so the analysis below is a built-in sample ' +
        'result based on the bundled sample contract, <b>not</b> a live model reading ' +
        'of your text. Load the sample contract to watch every quote verify end-to-end; ' +
        'paste different text and the sample quotes will be flagged as unverified — ' +
        'that checking layer is fully real. Set NEBIUS_API_KEY and restart for live ' +
        'Nemotron analysis.</div>';
    } else {
      $('status').innerHTML = '<div class="banner live"><b>LIVE MODE</b> — analyses run on ' +
        'Nebius Token Factory with NVIDIA Nemotron models (' + esc(d.models.nano) +
        ' for extraction, ' + esc(d.models.super) + ' for reasoning).</div>';
    }
  }catch(e){ /* status is informational only */ }
}

async function loadSample(){
  const r = await fetch('/api/sample');
  $('text').value = await r.text();
  updateCount();
}
function updateCount(){ $('count').textContent = $('text').value.length; }
$('text').addEventListener('input', updateCount);

function factsTable(f){
  const pay = f.payment || {};
  const rows = [
    ['Parties', (f.parties || []).join(' · ')],
    ['Effective date', f.effective_date],
    ['Term', f.term],
    ['Payment', [pay.amount, pay.schedule].filter(Boolean).join(' — ')],
    ['Deliverables', (f.deliverables || []).join('; ')],
    ['Deadlines', (f.deadlines || []).map(d => esc(d.what) + ' — ' + esc(d.when)).join('<br>')],
    ['Termination', f.termination],
    ['IP ownership', f.ip_ownership],
    ['Confidentiality', f.confidentiality],
  ];
  let h = '<table>';
  for(const [k, v] of rows){
    const val = (k === 'Deadlines') ? (v || '—') : esc(v || '—');
    h += '<tr><th>' + k + '</th><td>' + val + '</td></tr>';
  }
  return h + '</table>';
}

async function run(){
  const out = $('out'), btn = $('go');
  btn.disabled = true; btn.textContent = 'Analyzing...';
  out.innerHTML = '<p>Analyzing — extracting facts, reasoning about risk, verifying quotes...</p>';
  try{
    const r = await fetch('/api/analyze', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text: $('text').value})});
    const d = await r.json();
    if(!r.ok || d.error){ out.innerHTML = '<div class="error"><b>Could not analyze:</b> ' +
      esc(d.error || ('HTTP ' + r.status)) + '</div>'; return; }
    let h = '';
    if(d.mode === 'mock') h += '<div class="banner mock"><b>Offline demo result</b> — ' +
      'sample analysis (see the notice above), with quote verification run for real ' +
      'against the text you pasted.</div>';
    h += '<h2>Summary</h2><p>' + esc(d.summary || 'No summary returned.') + '</p>';
    h += '<h2>Key facts</h2>' + factsTable(d.facts || {});
    const verified = d.red_flags.filter(f => f.verified).length;
    h += '<h2>Red flags</h2>';
    if(d.red_flags.length === 0){
      h += '<p>No red flags were identified in this text.</p>';
    } else {
      h += '<p class="meta">' + verified + ' of ' + d.red_flags.length +
        ' quotes verified verbatim against your text.</p>';
      for(const f of d.red_flags){
        const sev = String(f.severity || 'low').toLowerCase();
        h += '<div class="flag ' + sev + '"><span class="pill ' + sev + '">' + esc(sev) +
          '</span> <b>' + esc(f.title) + '</b><br>' + esc(f.why) +
          '<blockquote>&ldquo;' + esc(f.quote) + '&rdquo;</blockquote>' +
          (f.verified
            ? '<span class="badge ok">&#10003; Quote verified — found verbatim in your text</span>'
            : '<span class="badge bad">&#10007; Quote NOT found in your text — treat this flag with suspicion</span>') +
          '</div>';
      }
    }
    if((d.obligations || []).length){
      h += '<h2>Your obligations &amp; deadlines</h2><ul>' +
        d.obligations.map(o => '<li>' + esc(o) + '</li>').join('') + '</ul>';
    }
    if((d.questions || []).length){
      h += '<h2>Questions to ask before you sign</h2><ul>' +
        d.questions.map(q => '<li>' + esc(q) + '</li>').join('') + '</ul>';
    }
    h += '<h2>Run details</h2><p class="meta">Mode: ' + esc(d.mode) +
      ' · Extraction model: ' + esc(d.models && d.models.extract) +
      ' · Reasoning model: ' + esc(d.models && d.models.reason);
    const u = d.usage || {};
    const fmt = x => x ? ('in ' + (x.prompt_tokens ?? '?') + ' / out ' + (x.completion_tokens ?? '?') + ' tokens') : 'n/a';
    h += '<br>Token usage — extraction: ' + fmt(u.extract) + ' · reasoning: ' + fmt(u.reason) + '</p>';
    h += '<p><i>' + esc(d.disclaimer) + '</i></p>';
    out.innerHTML = h;
  }catch(e){
    out.innerHTML = '<div class="error"><b>Request failed:</b> ' + esc(e.message) + '</div>';
  }finally{
    btn.disabled = false; btn.textContent = 'Analyze contract';
  }
}
loadStatus();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/status":
            client = TokenFactoryClient()
            self._send(200, json.dumps({"mode": client.mode, "models": MODELS}))
        elif self.path == "/api/sample":
            self._send(200, SAMPLE.read_text(encoding="utf-8"), "text/plain; charset=utf-8")
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/api/analyze":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
            result = analyze_contract(payload.get("text", ""))
            self._send(200, json.dumps(result))
        except Exception as e:  # surface errors honestly, never fabricate
            self._send(400, json.dumps({"error": str(e)}))

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
