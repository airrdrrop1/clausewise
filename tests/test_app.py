"""HTTP smoke tests for the demo server (no network beyond localhost,
no API key — the server runs in mock mode).

Covers the judge-facing surface: the page loads, the mode is reported
honestly, the sample endpoint works, valid analysis returns structured
JSON, and bad input gets a graceful 400 instead of a crash.
"""

import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as app_module

SAMPLE = (Path(__file__).parent.parent / "samples" / "freelance-contract-sample.txt").read_text()


def _request(base, method, path, body=None):
    data = None
    headers = {}
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


class Server:
    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_module.Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.base

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_page_and_status():
    with Server() as base:
        status, body = _request(base, "GET", "/")
        assert status == 200 and "ClauseWise" in body
        assert "OFFLINE DEMO MODE" in body  # banner copy ships in the page
        status, body = _request(base, "GET", "/api/status")
        data = json.loads(body)
        assert status == 200 and data["mode"] in ("mock", "live")
        assert "nano" in data["models"] and "super" in data["models"]


def test_sample_endpoint():
    with Server() as base:
        status, body = _request(base, "GET", "/api/sample")
        assert status == 200 and "FREELANCE DESIGN SERVICES AGREEMENT" in body


def test_analyze_sample_mock_mode():
    with Server() as base:
        status, body = _request(base, "POST", "/api/analyze", {"text": SAMPLE})
        data = json.loads(body)
        assert status == 200
        assert data["mode"] == "mock"
        assert data["summary"]
        assert len(data["red_flags"]) >= 3
        assert all(f["verified"] for f in data["red_flags"])


def test_analyze_rejects_bad_input_gracefully():
    with Server() as base:
        status, body = _request(base, "POST", "/api/analyze", {"text": "short"})
        assert status == 400 and "error" in json.loads(body)
        status, body = _request(base, "POST", "/api/analyze", b"{not json")
        assert status == 400 and "error" in json.loads(body)
        status, body = _request(base, "POST", "/api/analyze", {"text": 42})
        assert status == 400 and "error" in json.loads(body)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"all {len(tests)} tests passed")
