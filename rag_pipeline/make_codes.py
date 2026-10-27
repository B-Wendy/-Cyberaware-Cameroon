"""
make_codes.py  —  creates fresh random access codes to sell.

    python make_codes.py 20          # 20 new codes

Copy the line it prints into the ACCESS_CODES setting (in your .env file on your
computer, and in the Render dashboard for the online site), then give one code to
each customer after they pay.  Codes are checked on the server, never stored in
the code or in GitHub.  Use this again whenever you want to retire the old codes.
"""

import secrets
import sys

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"       # no 0/O or 1/I/L, so SMS codes are easy to read


def make_code() -> str:
    pick = lambda n: "".join(secrets.choice(ALPHABET) for _ in range(n))
    return f"CYB-{pick(4)}-{pick(4)}"


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    codes = [make_code() for _ in range(count)]
    print("\nYour new codes:\n")
    for c in codes:
        print("  ", c)
    print("\nLine for .env / Render (ACCESS_CODES):\n")
    print("ACCESS_CODES=" + ",".join(codes))
    print("\nTo make the long secret used to sign tokens (TOKEN_SECRET):\n")
    print("TOKEN_SECRET=" + secrets.token_urlsafe(48))
