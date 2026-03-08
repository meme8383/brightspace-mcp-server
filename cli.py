#!/usr/bin/env python3
"""
Brightspace CLI — query courses, assignments, grades, etc. from the terminal.

Usage:
    python cli.py courses
    python cli.py assignments [--course ID]
    python cli.py grades [--course ID]
    python cli.py announcements [--course ID]
    python cli.py quizzes [--course ID]
    python cli.py content [--course ID]
    python cli.py calendar [--course ID]
    python cli.py due [--days 7]
    python cli.py notify [--days 3]
    python cli.py watch [--interval 30] [--days 3]
"""

import argparse
import json
import sys
import time
import re
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from brightspace_api import BrightspaceScraper

DATA_DIR = Path(__file__).parent / ".cache"
SEEN_FILE = DATA_DIR / "seen.json"


# ── helpers ──────────────────────────────────────────────────────────

class session:
    """Context manager that opens a headless scraper and authenticates via cookies."""
    def __enter__(self):
        self.scraper = BrightspaceScraper(headless=True)
        self.scraper.__enter__()
        if not self.scraper.login_with_cookies():
            self.scraper.__exit__(None, None, None)
            print("Session expired. Refresh cookies and try again.", file=sys.stderr)
            sys.exit(1)
        return self.scraper

    def __exit__(self, *exc):
        self.scraper.__exit__(*exc)


def parse_date(s: str) -> datetime | None:
    """Best-effort parse of Brightspace date strings."""
    for fmt in (
        "%b %d, %Y %I:%M %p",
        "%b %d, %Y %I:%M:%S %p",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def course_url(cid: str) -> str:
    return f"/d2l/home/{cid}"


def pick_courses(scraper, course_id: str | None) -> list[tuple[str, str]]:
    """Return [(name, url), ...] for the given course or all courses."""
    if course_id:
        return [("", course_url(course_id))]
    courses = scraper.get_courses()
    return [(c.code or c.name, c.url) for c in courses]


def fmt_table(rows: list[list[str]], headers: list[str] | None = None):
    """Simple column-aligned table printer."""
    all_rows = ([headers] if headers else []) + rows
    if not all_rows:
        return
    widths = [max(len(str(r[i])) if i < len(r) else 0 for r in all_rows) for i in range(max(len(r) for r in all_rows))]
    def fmt_row(r):
        return "  ".join(str(r[i] if i < len(r) else "").ljust(widths[i]) for i in range(len(widths)))
    if headers:
        print(fmt_row(headers))
        print("  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt_row(r))


# ── notification state ───────────────────────────────────────────────

def load_seen() -> dict:
    DATA_DIR.mkdir(exist_ok=True)
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text())
    return {"announcements": {}, "grades": {}, "assignments": {}}


def save_seen(seen: dict):
    DATA_DIR.mkdir(exist_ok=True)
    SEEN_FILE.write_text(json.dumps(seen, indent=2))


def diff_announcements(course_name: str, new: list, seen: dict) -> list[str]:
    key = f"{course_name}"
    old_titles = set(seen.get("announcements", {}).get(key, []))
    seen.setdefault("announcements", {})[key] = [a.title for a in new]
    return [a for a in new if a.title not in old_titles]


def diff_grades(course_name: str, new: list, seen: dict) -> list[str]:
    key = f"{course_name}"
    old = {g["name"]: g["grade"] for g in seen.get("grades", {}).get(key, [])}
    seen.setdefault("grades", {})[key] = [{"name": g.name, "grade": g.grade} for g in new]
    changed = []
    for g in new:
        prev = old.get(g.name)
        if prev is not None and prev != g.grade and g.grade != "-%":
            changed.append(g)
        elif prev is None and g.grade and g.grade != "-%":
            changed.append(g)
    return changed


def diff_assignments(course_name: str, new: list, seen: dict) -> list[str]:
    key = f"{course_name}"
    old_scores = {a["title"]: a["score"] for a in seen.get("assignments", {}).get(key, [])}
    seen.setdefault("assignments", {})[key] = [{"title": a.title, "score": a.score} for a in new]
    changed = []
    for a in new:
        prev = old_scores.get(a.title)
        if prev is not None and prev != a.score and a.score and "/ 100 -" not in a.score:
            changed.append(a)
    return changed


# ── commands ─────────────────────────────────────────────────────────

def cmd_courses(args):
    with session() as s:
        courses = s.get_courses()
    rows = []
    for c in courses:
        cid = re.search(r'/(\d+)$', c.url)
        rows.append([cid.group(1) if cid else "", c.code, c.name[:60]])
    fmt_table(rows, ["ID", "Code", "Name"])


def cmd_assignments(args):
    with session() as s:
        for cname, curl in pick_courses(s, args.course):
            assignments = s.get_assignments(curl)
            if cname:
                print(f"\n--- {cname} ---")
            rows = [[a.title[:40], a.due_date[:25], a.status, a.score[:20]] for a in assignments]
            fmt_table(rows, ["Assignment", "Due", "Status", "Score"])


def cmd_grades(args):
    with session() as s:
        for cname, curl in pick_courses(s, args.course):
            grades = s.get_grades(curl)
            if cname:
                print(f"\n--- {cname} ---")
            rows = [[g.name[:40], g.points[:15], g.weight[:12], g.grade[:8], g.category[:25]] for g in grades]
            fmt_table(rows, ["Item", "Points", "Weight", "Grade", "Category"])


def cmd_announcements(args):
    with session() as s:
        for cname, curl in pick_courses(s, args.course):
            anns = s.get_announcements(curl)
            if cname:
                print(f"\n--- {cname} ---")
            rows = [[a.title[:60], a.date] for a in anns]
            fmt_table(rows, ["Title", "Date"])


def cmd_quizzes(args):
    with session() as s:
        for cname, curl in pick_courses(s, args.course):
            quizzes = s.get_quizzes(curl)
            if cname:
                print(f"\n--- {cname} ---")
            rows = [[q.name[:40], q.due_date[:25], q.attempts, q.status[:25]] for q in quizzes]
            fmt_table(rows, ["Quiz", "Due", "Attempts", "Status"])


def cmd_content(args):
    with session() as s:
        for cname, curl in pick_courses(s, args.course):
            modules = s.get_content(curl)
            if cname:
                print(f"\n--- {cname} ---")
            for m in modules:
                items = f" ({len(m.items)} items)" if m.items else ""
                print(f"  {m.name}{items}")
                for i in m.items:
                    print(f"    - {i}")


def cmd_calendar(args):
    with session() as s:
        for cname, curl in pick_courses(s, args.course):
            events = s.get_calendar(curl)
            if cname:
                print(f"\n--- {cname} ---")
            for e in events:
                print(f"  {e['time']:>10}  {e['title']}")


def cmd_due(args):
    """Show all items due within --days."""
    days = args.days
    cutoff = datetime.now() + timedelta(days=days)
    now = datetime.now()

    with session() as s:
        courses = s.get_courses()
        upcoming = []

        for c in courses:
            # Assignments
            for a in s.get_assignments(c.url):
                dt = parse_date(a.due_date)
                if dt and now <= dt <= cutoff:
                    upcoming.append((dt, c.code, "Assignment", a.title, a.status))

            # Quizzes
            for q in s.get_quizzes(c.url):
                dt = parse_date(q.due_date)
                if dt and now <= dt <= cutoff:
                    upcoming.append((dt, c.code, "Quiz", q.name, q.attempts))

    upcoming.sort(key=lambda x: x[0])
    if not upcoming:
        print(f"Nothing due in the next {days} days.")
        return
    rows = [[u[0].strftime("%a %b %d %I:%M%p"), u[1][:15], u[2], u[3][:40], str(u[4])] for u in upcoming]
    fmt_table(rows, ["Due", "Course", "Type", "Title", "Status"])


def cmd_notify(args):
    """Check for new announcements, grade changes, and upcoming due dates."""
    days = args.days
    cutoff = datetime.now() + timedelta(days=days)
    now = datetime.now()
    seen = load_seen()
    alerts = []

    with session() as s:
        courses = s.get_courses()
        for c in courses:
            cid = re.search(r'/(\d+)$', c.url)
            label = f"{c.code or c.name} ({cid.group(1)})" if cid else (c.code or c.name)
            state_key = cid.group(1) if cid else c.name

            # New announcements
            anns = s.get_announcements(c.url)
            new_anns = diff_announcements(state_key, anns, seen)
            for a in new_anns:
                alerts.append(f"[NEW] {label}: {a.title} ({a.date})")

            # Grade changes
            grades = s.get_grades(c.url)
            changed_grades = diff_grades(state_key, grades, seen)
            for g in changed_grades:
                alerts.append(f"[GRADE] {label}: {g.name} -> {g.grade} ({g.points})")

            # Assignment score updates
            assignments = s.get_assignments(c.url)
            changed_asgn = diff_assignments(state_key, assignments, seen)
            for a in changed_asgn:
                alerts.append(f"[SCORED] {label}: {a.title} -> {a.score}")

            # Upcoming due dates (assignments)
            for a in assignments:
                dt = parse_date(a.due_date)
                if dt and now <= dt <= cutoff and a.status == "Not Submitted":
                    delta = dt - now
                    urgency = "DUE TODAY" if delta.days == 0 else f"due in {delta.days}d"
                    alerts.append(f"[DUE] {label}: {a.title} ({urgency}, {a.due_date})")

            # Upcoming due dates (quizzes)
            quizzes = s.get_quizzes(c.url)
            for q in quizzes:
                dt = parse_date(q.due_date)
                if dt and now <= dt <= cutoff:
                    delta = dt - now
                    urgency = "DUE TODAY" if delta.days == 0 else f"due in {delta.days}d"
                    alerts.append(f"[DUE] {label}: {q.name} ({urgency}, {q.due_date})")

    save_seen(seen)

    if not alerts:
        print("No new notifications.")
    else:
        print(f"{len(alerts)} notification(s):\n")
        for a in alerts:
            print(f"  {a}")


def cmd_watch(args):
    """Poll for notifications every --interval minutes."""
    interval = args.interval
    print(f"Watching for changes every {interval} minutes. Ctrl-C to stop.\n")
    while True:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] Checking...")
        try:
            cmd_notify(args)
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
        print()
        time.sleep(interval * 60)


# ── main ─────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(prog="brightspace", description="Brightspace CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("courses", help="List enrolled courses")

    for name in ("assignments", "grades", "announcements", "quizzes", "content", "calendar"):
        sp = sub.add_parser(name, help=f"Show {name} for a course")
        sp.add_argument("--course", "-c", help="Course ID (omit for all courses)")

    sp_due = sub.add_parser("due", help="Show items due soon")
    sp_due.add_argument("--days", "-d", type=int, default=7, help="Days ahead (default: 7)")

    sp_notify = sub.add_parser("notify", help="Check for new announcements, grade changes, due dates")
    sp_notify.add_argument("--days", "-d", type=int, default=3, help="Days ahead for due date alerts (default: 3)")

    sp_watch = sub.add_parser("watch", help="Poll for notifications on an interval")
    sp_watch.add_argument("--interval", "-i", type=int, default=30, help="Minutes between checks (default: 30)")
    sp_watch.add_argument("--days", "-d", type=int, default=3, help="Days ahead for due date alerts (default: 3)")

    args = p.parse_args()
    cmd = {
        "courses": cmd_courses,
        "assignments": cmd_assignments,
        "grades": cmd_grades,
        "announcements": cmd_announcements,
        "quizzes": cmd_quizzes,
        "content": cmd_content,
        "calendar": cmd_calendar,
        "due": cmd_due,
        "notify": cmd_notify,
        "watch": cmd_watch,
    }
    cmd[args.command](args)


if __name__ == "__main__":
    main()
