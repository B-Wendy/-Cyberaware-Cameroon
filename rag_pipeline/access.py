"""
access.py
Server-side access control for CyberAware Cameroon.

WHY THIS FILE EXISTS
    The browser must never be the one that decides "this person has paid".
    (An early build kept a "premium" flag in the browser's localStorage and it
    could be switched on from the browser console.)  Here the SERVER decides.

HOW IT WORKS
    1. The customer pays and receives an access code (sent by SMS).
    2. The customer types the code into the website.
    3. The server checks the code against the list kept in environment
       variables (never in the source code, never in GitHub).
    4. If the code is right, the server hands back a TOKEN: a small piece of
       text that says "this person is a subscriber until <date>" and carries
       a signature made with a secret only the server knows.
    5. On every protected request the browser sends the token back.  The server
       re-checks the signature and the expiry date.  A forged or edited token
       fails the signature check, so it is rejected.

    The same signing method is used for a second token, the PROGRESS token,
    which records the best quiz score per lesson so a certificate can be issued
    without a database.

Environment variables used
    TOKEN_SECRET        secret used to sign tokens (long random text)
    ACCESS_CODES        subscriber codes, separated by commas
    ADMIN_ACCESS_CODE   one administrator/demo code (full access)
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

log = logging.getLogger("cyberaware.access")

SUBSCRIPTION_SECONDS = 30 * 24 * 3600   # one month of access per code entry
ADMIN_SECONDS        = 7 * 24 * 3600    # demo / evaluation access
TOKEN_VERSION        = "v1"

KIND_ACCESS   = "acc"
KIND_PROGRESS = "prg"

# Used only when TOKEN_SECRET is missing: a random secret that lives as long as
# the server process.  Tokens then stop working after every restart, which is
# annoying but safe (it can never fall back to a guessable secret).
_ephemeral_secret = secrets.token_bytes(32)
_warned = False


def _secret() -> bytes:
    global _warned
    value = os.getenv("TOKEN_SECRET", "").strip()
    if value:
        return value.encode("utf-8")
    if not _warned:
        log.warning("TOKEN_SECRET is not set: using a temporary secret. "
                    "Tokens will stop working when the server restarts.")
        _warned = True
    return _ephemeral_secret


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(message: str) -> str:
    return _b64(hmac.new(_secret(), message.encode("ascii"), hashlib.sha256).digest())


# ──────────────────────────────────────────────────────────────
# Tokens
# ──────────────────────────────────────────────────────────────

def make_token(kind: str, payload: dict) -> str:
    """Build  v1.<payload>.<signature>  where the signature covers the payload."""
    body = dict(payload)
    body["k"] = kind
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    head = f"{TOKEN_VERSION}.{_b64(raw)}"
    return f"{head}.{_sign(head)}"


def read_token(token, kind: str):
    """Return the payload dict if the token is genuine, otherwise None.

    Genuine means: right shape, signature matches, and it is the right KIND of
    token (a progress token can never be used as an access token).
    Expiry is NOT checked here; see access_status().
    """
    if not token or not isinstance(token, str) or len(token) > 4096:
        return None
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_VERSION:
        return None
    head = f"{parts[0]}.{parts[1]}"
    expected = _sign(head)
    if not hmac.compare_digest(expected.encode("ascii"), parts[2].encode("ascii", "ignore")):
        return None
    try:
        payload = json.loads(_unb64(parts[1]))
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("k") != kind:
        return None
    return payload


# ──────────────────────────────────────────────────────────────
# Access codes -> access token
# ──────────────────────────────────────────────────────────────

def _configured_codes() -> list:
    raw = os.getenv("ACCESS_CODES", "")
    codes = [c.strip().upper() for c in raw.replace("\n", ",").replace(";", ",").split(",")]
    return [c for c in codes if c]


def _admin_code() -> str:
    return os.getenv("ADMIN_ACCESS_CODE", "").strip().upper()


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def check_code(code: str):
    """Return "admin", "sub" or None for a typed code.

    Secure by default: if no codes are configured nothing is accepted.
    Every configured code is compared (no early exit) so the time taken does
    not reveal which code was close.
    """
    typed = (code or "").strip().upper()
    if not typed or len(typed) > 64:
        return None
    tier = None
    admin = _admin_code()
    if admin and _same(typed, admin):
        tier = "admin"
    for c in _configured_codes():
        if _same(typed, c) and tier is None:
            tier = "sub"
    return tier


def issue_access_token(tier: str, now: float = None) -> dict:
    now = int(now if now is not None else time.time())
    ttl = ADMIN_SECONDS if tier == "admin" else SUBSCRIPTION_SECONDS
    payload = {"tier": tier, "iat": now, "exp": now + ttl}
    return {"token": make_token(KIND_ACCESS, payload), "tier": tier, "expires_at": payload["exp"]}


def access_status(token, now: float = None):
    """Return (status, payload).

    status is one of:
        "none"     no token was sent
        "invalid"  token is forged, damaged or the wrong kind
        "expired"  genuine token but the subscription period is over
        "valid"    genuine and still in date
    """
    if not token:
        return "none", None
    payload = read_token(token, KIND_ACCESS)
    if payload is None:
        return "invalid", None
    now = now if now is not None else time.time()
    try:
        if float(payload.get("exp", 0)) <= now:
            return "expired", payload
    except (TypeError, ValueError):
        return "invalid", None
    return "valid", payload


def is_entitled(token, now: float = None) -> bool:
    return access_status(token, now)[0] == "valid"


# ──────────────────────────────────────────────────────────────
# Progress token (best quiz score per lesson)
# ──────────────────────────────────────────────────────────────

def read_progress(token) -> dict:
    """Return {lesson_id(int): best_score(int)}; an invalid token gives {}."""
    payload = read_token(token, KIND_PROGRESS)
    if not payload:
        return {}
    best = {}
    raw = payload.get("best", {})
    if isinstance(raw, dict):
        for key, value in raw.items():
            try:
                best[int(key)] = int(value)
            except (TypeError, ValueError):
                continue
    return best


def issue_progress_token(best: dict, now: float = None) -> str:
    payload = {"best": {str(k): int(v) for k, v in sorted(best.items())},
               "iat": int(now if now is not None else time.time())}
    return make_token(KIND_PROGRESS, payload)


def certificate_reference(name: str, completed_on: str, best: dict) -> str:
    """Short verification reference printed on the certificate.

    It is derived from the name, the date and the scores with the server
    secret, so it cannot be produced by anyone who does not hold the secret.
    """
    scores = ",".join(f"{k}:{best[k]}" for k in sorted(best))
    digest = hmac.new(_secret(), f"cert|{name}|{completed_on}|{scores}".encode("utf-8"),
                      hashlib.sha256).hexdigest()
    return "CAC-" + digest[:10].upper()
