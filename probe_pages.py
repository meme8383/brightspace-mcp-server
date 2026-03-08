#!/usr/bin/env python3
"""Probe Brightspace assignment page structure."""

from pathlib import Path
from brightspace_api import BrightspaceScraper

COURSE_ID = ""  # Set your course ID here
BASE = "https://purdue.brightspace.com"
URL = f"{BASE}/d2l/lms/dropbox/user/folders_list.d2l?ou={COURSE_ID}"

OUT_DIR = Path("probe_output")
OUT_DIR.mkdir(exist_ok=True)

with BrightspaceScraper(headless=True) as scraper:
    if not scraper.login_with_cookies():
        print("Cookie login failed")
        exit(1)

    print(f"Loading: {URL}")
    scraper.page.goto(URL, wait_until="networkidle", timeout=20000)
    print(f"URL after load: {scraper.page.url}")
    print(f"Title: {scraper.page.title()}")

    scraper.page.screenshot(path=str(OUT_DIR / "assignments.png"), full_page=True)

    html = scraper.page.content()
    (OUT_DIR / "assignments.html").write_text(html)
    print(f"HTML length: {len(html)}")

    # Dump table structure
    tables = scraper.page.query_selector_all("table")
    print(f"\nTables: {len(tables)}")
    for i, t in enumerate(tables):
        cls = t.get_attribute("class") or ""
        tid = t.get_attribute("id") or ""
        rows = t.query_selector_all("tr")
        print(f"  table[{i}]: class='{cls}' id='{tid}' rows={len(rows)}")

    # Look for common assignment-like selectors
    for sel in ["tr.d_ich", "tr[class*='d_g']", ".dco", ".d2l-datalist-item",
                "a[href*='dropbox']", "a[href*='folder']", ".d2l-foldername",
                "th", ".d_gn", ".d_gt"]:
        els = scraper.page.query_selector_all(sel)
        if els:
            print(f"  '{sel}': {len(els)}")
            for e in els[:5]:
                txt = (e.text_content() or "").strip()[:120]
                if txt:
                    print(f"    → {txt}")

print(f"\nSaved to {OUT_DIR}/")
