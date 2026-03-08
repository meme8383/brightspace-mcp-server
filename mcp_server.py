#!/usr/bin/env python3
"""
Brightspace MCP Server — exposes Brightspace data as tools for Claude.
"""

import asyncio
import json
from dataclasses import asdict
from functools import partial
from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.types import Tool

from brightspace_api import BrightspaceScraper

server = Server("brightspace")

TOOLS = [
    Tool(
        name="brightspace_courses",
        description="List all enrolled Brightspace courses",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="brightspace_assignments",
        description="Get assignments for a course. Returns title, due date, status, score, feedback.",
        inputSchema={
            "type": "object",
            "properties": {"course_id": {"type": "string", "description": "Numeric course ID"}},
            "required": ["course_id"],
        },
    ),
    Tool(
        name="brightspace_grades",
        description="Get grade items for a course. Returns name, points, weight, grade percentage.",
        inputSchema={
            "type": "object",
            "properties": {"course_id": {"type": "string", "description": "Numeric course ID"}},
            "required": ["course_id"],
        },
    ),
    Tool(
        name="brightspace_announcements",
        description="Get announcements for a course.",
        inputSchema={
            "type": "object",
            "properties": {"course_id": {"type": "string", "description": "Numeric course ID"}},
            "required": ["course_id"],
        },
    ),
    Tool(
        name="brightspace_quizzes",
        description="Get quizzes for a course. Returns name, due date, attempts, status.",
        inputSchema={
            "type": "object",
            "properties": {"course_id": {"type": "string", "description": "Numeric course ID"}},
            "required": ["course_id"],
        },
    ),
    Tool(
        name="brightspace_content",
        description="Get course content modules and topics.",
        inputSchema={
            "type": "object",
            "properties": {"course_id": {"type": "string", "description": "Numeric course ID"}},
            "required": ["course_id"],
        },
    ),
    Tool(
        name="brightspace_calendar",
        description="Get today's calendar events for a course.",
        inputSchema={
            "type": "object",
            "properties": {"course_id": {"type": "string", "description": "Numeric course ID"}},
            "required": ["course_id"],
        },
    ),
    Tool(
        name="brightspace_due",
        description="Get all items due across all courses within a number of days.",
        inputSchema={
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Days ahead to check (default 7)"}},
            "required": [],
        },
    ),
]


def _run_sync(fn):
    """Run a synchronous scraper function in a thread."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, fn)


def _scraper_call(method_name: str, course_id: str | None = None):
    """Open a scraper session, authenticate, call a method, return serialized results."""
    with BrightspaceScraper(headless=True) as s:
        if not s.login_with_cookies():
            return [{"type": "text", "text": "Session expired. Refresh cookies (.cookies.json) and try again."}]

        if course_id:
            result = getattr(s, method_name)(f"/d2l/home/{course_id}")
        else:
            result = getattr(s, method_name)()

        if isinstance(result, list):
            data = [asdict(item) if hasattr(item, '__dataclass_fields__') else item for item in result]
        else:
            data = result

        return [{"type": "text", "text": json.dumps(data, indent=2, default=str)}]


def _due_items(days: int = 7):
    """Get all upcoming due items across all courses."""
    from datetime import datetime, timedelta
    cutoff = datetime.now() + timedelta(days=days)
    now = datetime.now()

    with BrightspaceScraper(headless=True) as s:
        if not s.login_with_cookies():
            return [{"type": "text", "text": "Session expired."}]

        courses = s.get_courses()
        upcoming = []

        for c in courses:
            from cli import parse_date
            for a in s.get_assignments(c.url):
                dt = parse_date(a.due_date)
                if dt and now <= dt <= cutoff:
                    upcoming.append({"due": a.due_date, "course": c.code, "type": "Assignment",
                                     "title": a.title, "status": a.status})
            for q in s.get_quizzes(c.url):
                dt = parse_date(q.due_date)
                if dt and now <= dt <= cutoff:
                    upcoming.append({"due": q.due_date, "course": c.code, "type": "Quiz",
                                     "title": q.name, "attempts": q.attempts})

        upcoming.sort(key=lambda x: x["due"])
        return [{"type": "text", "text": json.dumps(upcoming, indent=2)}]


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[dict]:
    dispatch = {
        "brightspace_courses": lambda: _scraper_call("get_courses"),
        "brightspace_assignments": lambda: _scraper_call("get_assignments", arguments.get("course_id")),
        "brightspace_grades": lambda: _scraper_call("get_grades", arguments.get("course_id")),
        "brightspace_announcements": lambda: _scraper_call("get_announcements", arguments.get("course_id")),
        "brightspace_quizzes": lambda: _scraper_call("get_quizzes", arguments.get("course_id")),
        "brightspace_content": lambda: _scraper_call("get_content", arguments.get("course_id")),
        "brightspace_calendar": lambda: _scraper_call("get_calendar", arguments.get("course_id")),
        "brightspace_due": lambda: _due_items(arguments.get("days", 7)),
    }

    fn = dispatch.get(name)
    if not fn:
        return [{"type": "text", "text": f"Unknown tool: {name}"}]

    return await _run_sync(fn)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="brightspace",
                server_version="2.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
