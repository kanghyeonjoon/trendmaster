#!/usr/bin/env python3
"""
Google Calendar MCP Server
Exposes calendar tools to Claude Code - no extra Claude API costs required.
"""

import json
import os
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_PATH = Path(__file__).parent / "token.json"
CREDENTIALS_PATH = Path(__file__).parent / "credentials.json"
DEFAULT_CALENDAR_ID = os.environ.get("CALENDAR_ID", "primary")
DEFAULT_TIMEZONE = os.environ.get("TIMEZONE", "Asia/Seoul")


def get_calendar_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}. "
                    "Download it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def parse_datetime(dt_str: str, timezone: str) -> str:
    """Parse various datetime formats and return RFC3339 string."""
    tz = ZoneInfo(timezone)
    now = datetime.datetime.now(tz)

    # Handle relative expressions
    dt_str = dt_str.strip().lower()

    # Try ISO format first
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"]:
        try:
            dt = datetime.datetime.strptime(dt_str, fmt)
            return dt.replace(tzinfo=tz).isoformat()
        except ValueError:
            pass

    raise ValueError(f"Cannot parse datetime: {dt_str}. Use format: YYYY-MM-DD HH:MM")


app = Server("calendar-mcp")


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="create_event",
            description=(
                "Create a Google Calendar event. Use this when the user mentions scheduling, "
                "meetings, appointments, reminders, or any time-based plans."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title/summary"},
                    "start": {
                        "type": "string",
                        "description": "Start datetime in format YYYY-MM-DD HH:MM",
                    },
                    "end": {
                        "type": "string",
                        "description": "End datetime in format YYYY-MM-DD HH:MM",
                    },
                    "description": {"type": "string", "description": "Event description (optional)"},
                    "location": {"type": "string", "description": "Event location (optional)"},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee email addresses (optional)",
                    },
                    "timezone": {
                        "type": "string",
                        "description": f"Timezone (default: {DEFAULT_TIMEZONE})",
                    },
                },
                "required": ["title", "start", "end"],
            },
        ),
        Tool(
            name="list_events",
            description="List upcoming Google Calendar events.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look ahead (default: 7)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of events to return (default: 10)",
                    },
                },
            },
        ),
        Tool(
            name="delete_event",
            description="Delete a Google Calendar event by event ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "Event ID to delete"},
                },
                "required": ["event_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    service = get_calendar_service()
    tz = arguments.get("timezone", DEFAULT_TIMEZONE)

    if name == "create_event":
        start_dt = parse_datetime(arguments["start"], tz)
        end_dt = parse_datetime(arguments["end"], tz)

        body = {
            "summary": arguments["title"],
            "start": {"dateTime": start_dt, "timeZone": tz},
            "end": {"dateTime": end_dt, "timeZone": tz},
        }
        if arguments.get("description"):
            body["description"] = arguments["description"]
        if arguments.get("location"):
            body["location"] = arguments["location"]
        if arguments.get("attendees"):
            body["attendees"] = [{"email": e} for e in arguments["attendees"]]

        event = service.events().insert(calendarId=DEFAULT_CALENDAR_ID, body=body).execute()
        return [
            TextContent(
                type="text",
                text=(
                    f"Event created successfully!\n"
                    f"Title: {event['summary']}\n"
                    f"Start: {event['start'].get('dateTime', event['start'].get('date'))}\n"
                    f"End: {event['end'].get('dateTime', event['end'].get('date'))}\n"
                    f"Event ID: {event['id']}\n"
                    f"Link: {event.get('htmlLink', 'N/A')}"
                ),
            )
        ]

    elif name == "list_events":
        days = arguments.get("days", 7)
        max_results = arguments.get("max_results", 10)
        now = datetime.datetime.utcnow().isoformat() + "Z"
        future = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat() + "Z"

        result = (
            service.events()
            .list(
                calendarId=DEFAULT_CALENDAR_ID,
                timeMin=now,
                timeMax=future,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = result.get("items", [])
        if not events:
            return [TextContent(type="text", text=f"No events found in the next {days} days.")]

        lines = [f"Upcoming events (next {days} days):\n"]
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date"))
            lines.append(f"- [{e['id']}] {e['summary']} @ {start}")

        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "delete_event":
        service.events().delete(
            calendarId=DEFAULT_CALENDAR_ID, eventId=arguments["event_id"]
        ).execute()
        return [TextContent(type="text", text=f"Event {arguments['event_id']} deleted.")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
