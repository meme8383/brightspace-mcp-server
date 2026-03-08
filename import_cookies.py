#!/usr/bin/env python3
"""
Import browser cookies into Playwright format for headless reuse.

Usage:
  1. Install "Cookie-Editor" extension in your browser
  2. Log into https://purdue.brightspace.com
  3. Click Cookie-Editor → Export → JSON
  4. Save/paste the JSON into a file (e.g. raw_cookies.json)
  5. Run: python import_cookies.py raw_cookies.json

The script converts the cookies to Playwright's format and writes .cookies.json
"""

import json
import sys
from pathlib import Path

COOKIE_FILE = Path(__file__).parent / ".cookies.json"


def convert_cookie(c: dict) -> dict:
    """Convert a browser-extension cookie to Playwright format."""
    pw = {
        "name": c["name"],
        "value": c["value"],
        "domain": c.get("domain", ""),
        "path": c.get("path", "/"),
        "secure": c.get("secure", False),
        "httpOnly": c.get("httpOnly", False),
        "sameSite": c.get("sameSite", "Lax"),
    }

    # Handle expiration — Playwright wants "expires" as a unix timestamp (float).
    # Browser extensions may export "expirationDate", "expires", or "expiry".
    for key in ("expirationDate", "expires", "expiry"):
        if key in c and c[key]:
            pw["expires"] = float(c[key])
            break

    # Playwright sameSite must be one of "Strict", "Lax", "None"
    ss = pw["sameSite"]
    if isinstance(ss, str):
        pw["sameSite"] = ss.capitalize() if ss.lower() in ("strict", "lax", "none") else "Lax"
    else:
        pw["sameSite"] = "Lax"

    return pw


def main():
    if len(sys.argv) < 2:
        # No file arg — read from stdin
        print("Paste your cookie JSON (Ctrl-D when done):")
        raw = sys.stdin.read()
    else:
        raw = Path(sys.argv[1]).read_text()

    cookies = json.loads(raw)

    if not isinstance(cookies, list):
        print("Error: expected a JSON array of cookies")
        sys.exit(1)

    converted = [convert_cookie(c) for c in cookies]
    COOKIE_FILE.write_text(json.dumps(converted, indent=2))
    print(f"Wrote {len(converted)} cookies to {COOKIE_FILE}")
    print("Now run: python brightspace_api.py")


if __name__ == "__main__":
    main()
