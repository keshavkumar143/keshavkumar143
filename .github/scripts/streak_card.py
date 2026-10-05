import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

GRAPHQL_URL = "https://api.github.com/graphql"

YEARS_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection { contributionYears }
  }
}
"""

CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

THEME = {
    "background": "#1a1b27",
    "stroke": "#70a5fd",
    "ring": "#bf91f3",
    "fire": "#bf91f3",
    "numbers": "#38bdae",
    "labels": "#70a5fd",
    "dates": "#38bdae",
}

FONT = "'Segoe UI', Ubuntu, sans-serif"

FIRE_PATH = (
    "M13.5.67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73"
    "l.03-.36C5.21 7.51 4 10.62 4 14c0 4.42 3.58 8 8 8s8-3.58 8-8C20 8.61 17.41 3.8 13.5.67z"
    "M11.71 19c-1.78 0-3.22-1.4-3.22-3.14 0-1.62 1.05-2.76 2.81-3.12 1.77-.36 3.6-1.21 "
    "4.62-2.58.39 1.29.59 2.65.59 4.04 0 2.65-2.15 4.8-4.8 4.8z"
)


@dataclass
class Streak:
    length: int = 0
    start: date | None = None
    end: date | None = None


@dataclass
class Stats:
    total: int
    first_contribution: date | None
    current: Streak
    longest: Streak


def run_query(token: str, query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"GitHub API error: {payload['errors']}")
    return payload["data"]


def fetch_contributions(token: str, login: str, today: date) -> dict[date, int]:
    years_data = run_query(token, YEARS_QUERY, {"login": login})
    years = set(years_data["user"]["contributionsCollection"]["contributionYears"])
    years.add(today.year)

    contributions: dict[date, int] = {}
    for year in sorted(years):
        variables = {
            "login": login,
            "from": f"{year}-01-01T00:00:00Z",
            "to": f"{year}-12-31T23:59:59Z",
        }
        data = run_query(token, CALENDAR_QUERY, variables)
        weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for day in week["contributionDays"]:
                contributions[date.fromisoformat(day["date"])] = day["contributionCount"]
    return contributions


def compute_stats(contributions: dict[date, int], today: date) -> Stats:
    total = 0
    first_contribution = None
    current = Streak()
    longest = Streak()

    for day in sorted(d for d in contributions if d <= today):
        count = contributions[day]
        total += count
        if count > 0:
            first_contribution = first_contribution or day
            if current.length == 0:
                current.start = day
            current.length += 1
            current.end = day
            if current.length > longest.length:
                longest = Streak(current.length, current.start, current.end)
        elif day != today:
            current = Streak()

    return Stats(total, first_contribution, current, longest)


def format_day(day: date, today: date) -> str:
    label = f"{day:%b} {day.day}"
    if day.year != today.year:
        label += f", {day.year}"
    return label


def format_range(streak: Streak, today: date) -> str:
    if streak.length == 0 or streak.start is None or streak.end is None:
        return format_day(today, today)
    if streak.start == streak.end:
        return format_day(streak.start, today)
    return f"{format_day(streak.start, today)} - {format_day(streak.end, today)}"


def text(x: float, y: float, value: str, color: str, size: int, weight: int = 400) -> str:
    return (
        f"<text x='{x}' y='{y}' text-anchor='middle' fill='{color}' "
        f"font-family=\"{FONT}\" font-weight='{weight}' font-size='{size}px'>{value}</text>"
    )


def render_svg(stats: Stats, today: date) -> str:
    total_range = "No contributions yet"
    if stats.first_contribution:
        total_range = f"{format_day(stats.first_contribution, today)} - Present"

    parts = [
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 495 195' width='495' height='195'>",
        "<defs><mask id='ring-gap'>"
        "<rect width='495' height='195' fill='white'/>"
        "<ellipse cx='247.5' cy='32' rx='13' ry='18' fill='black'/>"
        "</mask></defs>",
        f"<rect x='0' y='0' width='495' height='195' rx='4.5' fill='{THEME['background']}'/>",
        f"<line x1='165' y1='28' x2='165' y2='170' stroke='{THEME['stroke']}' stroke-opacity='0.25'/>",
        f"<line x1='330' y1='28' x2='330' y2='170' stroke='{THEME['stroke']}' stroke-opacity='0.25'/>",
        text(82.5, 80, f"{stats.total:,}", THEME["numbers"], 28, 700),
        text(82.5, 116, "Total Contributions", THEME["labels"], 14),
        text(82.5, 146, total_range, THEME["dates"], 12),
        f"<circle cx='247.5' cy='71' r='40' fill='none' stroke='{THEME['ring']}' "
        "stroke-width='5' mask='url(#ring-gap)'/>",
        f"<path transform='translate(235.5 19.5)' fill='{THEME['fire']}' d='{FIRE_PATH}'/>",
        text(247.5, 81, f"{stats.current.length:,}", THEME["numbers"], 28, 700),
        text(247.5, 140, "Current Streak", THEME["labels"], 14, 700),
        text(247.5, 166, format_range(stats.current, today), THEME["dates"], 12),
        text(412.5, 80, f"{stats.longest.length:,}", THEME["numbers"], 28, 700),
        text(412.5, 116, "Longest Streak", THEME["labels"], 14),
        text(412.5, 146, format_range(stats.longest, today), THEME["dates"], 12),
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main() -> int:
    token = os.environ["GITHUB_TOKEN"]
    login = os.environ["USERNAME"]
    timezone = ZoneInfo(os.environ.get("TIMEZONE", "UTC"))
    output = Path(os.environ.get("OUTPUT", "streak-card/streak.svg"))

    today = datetime.now(timezone).date()
    contributions = fetch_contributions(token, login, today)
    stats = compute_stats(contributions, today)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_svg(stats, today))
    print(
        f"total={stats.total} current={stats.current.length} "
        f"longest={stats.longest.length} today={today}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
