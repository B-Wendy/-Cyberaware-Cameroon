"""
check_deployment.py  —  a quick health and security check of a RUNNING copy of the site.

Use it on your computer and again on the public Render address:

    python check_deployment.py http://127.0.0.1:8000
    python check_deployment.py https://your-app.onrender.com

It only uses Python's built-in tools (nothing to install).  It sends a few harmless
requests and prints PASS / FAIL for each.  It does NOT cost any model calls: the
test questions are gibberish, so the chatbot answers with its built-in fallback.
"""

import json
import sys
import urllib.error
import urllib.request

results = []


def call(base, method, path, body=None, headers=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok or not detail else f"   -> {detail}"))


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    base = sys.argv[1].rstrip("/")
    print(f"Checking {base}\n(the first request can take about a minute if the site was asleep)\n")

    status, headers, body = call(base, "GET", "/api/health", timeout=120)
    check("health endpoint answers 200 and the knowledge base is ready", status == 200 and '"knowledge_base_ready":true' in body.replace(" ", ""), f"{status} {body[:120]}")

    status, headers, body = call(base, "GET", "/")
    h = {k.lower(): v for k, v in headers.items()}
    check("home page loads", status == 200 and "CyberAware" in body)
    check("home page is small (under 200 KB)", len(body.encode()) < 200 * 1024, f"{len(body.encode())} bytes")
    check("security header: X-Content-Type-Options", h.get("x-content-type-options") == "nosniff")
    check("security header: X-Frame-Options", h.get("x-frame-options") == "DENY")
    check("security header: Content-Security-Policy", "default-src" in h.get("content-security-policy", ""))
    if base.startswith("https://"):
        check("security header: Strict-Transport-Security (HTTPS only)", "max-age" in h.get("strict-transport-security", ""))
    check("lessons are not inside the page", "mtn-verify-cm" not in body and "quiz:[" not in body)

    status, _h, body = call(base, "GET", "/api/lessons")
    cat = json.loads(body) if status == 200 else {}
    locked = [l["locked"] for l in cat.get("lessons", [])]
    check("catalogue lists 10 lessons, 8 locked", locked == [False, False] + [True] * 8, str(locked))
    check("catalogue contains no quiz answers", '"cor"' not in body and '"quiz"' not in body)

    for lesson in (2, 5, 9):
        status, _h, body = call(base, "GET", f"/api/lessons/{lesson}")
        check(f"locked lesson {lesson + 1} gives 402 and no content", status == 402 and "quiz" not in body, f"{status}")
    status, _h, body = call(base, "GET", "/api/lessons/0")
    check("free lesson 1 opens", status == 200 and '"quiz"' in body)
    for fake in ("1", "true", "premium", "v1.e30.AAAA"):
        status, _h, _b = call(base, "GET", "/api/lessons/5", headers={"X-Access-Token": fake})
        check(f"fake token '{fake}' does not unlock anything", status == 402, str(status))

    status, _h, _b = call(base, "POST", "/api/subscribe", {"code": "CYBER-001"})
    check("old hard-coded code CYBER-001 is rejected", status == 403, str(status))
    status, _h, _b = call(base, "POST", "/api/chat", {"message": "a" * 501, "language": "en"})
    check("question longer than 500 characters is rejected", status == 422, str(status))
    status, _h, body = call(base, "POST", "/api/chat", {"message": "<script>alert(1)</script>", "language": "en"})
    check("a question containing HTML is handled as plain text", status == 200 and "application/json" in str(_h.get("Content-Type", _h.get("content-type", ""))), str(status))

    # Rate limiting must hold even if the visitor invents X-Forwarded-For values.
    codes = []
    for i in range(24):
        s, _h, _b = call(base, "POST", "/api/chat", {"message": "zzzqx", "language": "en"},
                         headers={"X-Forwarded-For": f"10.9.8.{i}"})
        codes.append(s)
    check("chat rate limit (20/minute) works and cannot be dodged with fake headers", 429 in codes, str(codes))

    codes = []
    for i in range(8):
        s, _h, _b = call(base, "POST", "/api/subscribe", {"code": f"GUESS-{i}"}, headers={"X-Forwarded-For": f"10.7.6.{i}"})
        codes.append(s)
    check("access-code guessing is rate limited (5/minute)", 429 in codes, str(codes))

    for path in ("/validate-code", "/chat", "/.env", "/app.py"):
        s, _h, b = call(base, "GET", path)
        check(f"{path} is not exposed", s in (404, 405) and "GROQ" not in b, str(s))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
