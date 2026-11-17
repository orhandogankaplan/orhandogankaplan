#!/usr/bin/env python3
"""Render personalized SVG cards for the orhandogankaplan GitHub profile.

Uses only public GitHub profile, repository, and contribution-calendar data.
No authentication token or third-party Python packages are required.
"""
from __future__ import annotations

import argparse
import calendar
import html
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

USER = "orhandogankaplan"
API = "https://api.github.com"
GREEN = "#39d353"
BG = "#0d1117"
PANEL = "#111820"
BORDER = "#263238"
INK = "#e6f0e8"
MUTED = "#9aa89e"
FAINT = "#68786d"


class ContributionParser(HTMLParser):
    """Collect GitHub calendar cells and their accessible contribution counts."""

    def __init__(self) -> None:
        super().__init__()
        self.cells: list[dict[str, object]] = []
        self.cell_dates: dict[str, str] = {}
        self.tooltip_for: str | None = None
        self.tooltip_text: list[str] = []
        self.counts: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "td" and values.get("data-date") and values.get("data-level") is not None:
            cell_date = values["data-date"]
            try:
                level = int(values["data-level"] or "0")
                date.fromisoformat(cell_date or "")
            except ValueError:
                return
            cell_id = values.get("id")
            self.cells.append({"date": cell_date, "level": max(0, min(level, 4)), "count": 0})
            if cell_id:
                self.cell_dates[cell_id] = cell_date or ""
        elif tag == "tool-tip" and values.get("for"):
            self.tooltip_for = values["for"]
            self.tooltip_text = []

    def handle_data(self, data: str) -> None:
        if self.tooltip_for:
            self.tooltip_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "tool-tip" or not self.tooltip_for:
            return
        cell_date = self.cell_dates.get(self.tooltip_for)
        text = " ".join(self.tooltip_text)
        match = re.search(r"(\d+)\s+contributions?", text, re.IGNORECASE)
        count = int(match.group(1)) if match else 0
        if cell_date:
            self.counts[cell_date] = count
        self.tooltip_for = None
        self.tooltip_text = []


def fetch_bytes(url: str, accept: str = "text/html") -> bytes:
    request = Request(url, headers={"User-Agent": "orhandogankaplan-profile-art/1.0", "Accept": accept})
    try:
        with urlopen(request, timeout=25) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not read public GitHub data from {url}: {exc}") from exc


def fetch_json(url: str) -> object:
    return json.loads(fetch_bytes(url, "application/vnd.github+json").decode("utf-8"))


def fetch_profile() -> tuple[dict[str, object], list[dict[str, object]]]:
    profile = fetch_json(f"{API}/users/{USER}")
    repos = fetch_json(f"{API}/users/{USER}/repos?type=owner&sort=updated&direction=desc&per_page=100")
    if not isinstance(profile, dict) or not isinstance(repos, list):
        raise RuntimeError("GitHub returned an unexpected profile response.")
    return profile, [repo for repo in repos if isinstance(repo, dict)]


def fetch_contributions() -> list[dict[str, object]]:
    page = fetch_bytes(f"https://github.com/users/{USER}/contributions").decode("utf-8", "replace")
    parser = ContributionParser()
    parser.feed(page)
    if not parser.cells:
        raise RuntimeError("GitHub's public contribution calendar was not found.")
    for cell in parser.cells:
        cell_date = str(cell["date"])
        cell["count"] = parser.counts.get(cell_date, 0)
    return sorted(parser.cells, key=lambda cell: str(cell["date"]))


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def write_svg(output: Path, name: str, svg: str) -> None:
    path = output / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def display_name(profile: dict[str, object]) -> str:
    return str(profile.get("name") or USER)


def current_streak(days: list[dict[str, object]]) -> int:
    counts = {date.fromisoformat(str(day["date"])): int(day["count"]) for day in days}
    today = datetime.now(timezone.utc).date()
    cursor = min(today, max(counts))
    if counts.get(cursor, 0) == 0 and counts.get(cursor - timedelta(days=1), 0) > 0:
        cursor -= timedelta(days=1)
    streak = 0
    while counts.get(cursor, 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak(days: list[dict[str, object]]) -> int:
    best = run = 0
    previous: date | None = None
    for day in days:
        current = date.fromisoformat(str(day["date"]))
        if int(day["count"]) > 0:
            run = run + 1 if previous and current == previous + timedelta(days=1) else 1
            best = max(best, run)
        else:
            run = 0
        previous = current
    return best


def monthly_totals(days: list[dict[str, object]]) -> list[tuple[str, int]]:
    if not days:
        return []
    last_day = date.fromisoformat(str(days[-1]["date"]))
    first_month = (last_day.replace(day=1) - timedelta(days=335)).replace(day=1)
    totals: dict[str, int] = defaultdict(int)
    for item in days:
        item_date = date.fromisoformat(str(item["date"]))
        key = item_date.strftime("%Y-%m")
        totals[key] += int(item["count"])
    months: list[tuple[str, int]] = []
    cursor = first_month
    while cursor <= last_day.replace(day=1):
        key = cursor.strftime("%Y-%m")
        months.append((cursor.strftime("%b"), totals.get(key, 0)))
        year, month = cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1
        cursor = date(year, month, 1)
    return months[-12:]


def hero_svg(profile: dict[str, object], project_count: int) -> str:
    name = esc(display_name(profile))
    bio = "IT Systems &amp; Technologies student · Python · Automation"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="365" viewBox="0 0 1200 365" role="img" aria-labelledby="title desc">
<title id="title">{name} — profile</title><desc id="desc">IT Systems and Technologies student building Python tools and automation projects.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0b1110"/><stop offset="1" stop-color="#151c18"/></linearGradient><linearGradient id="accent" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{GREEN}"/><stop offset="1" stop-color="#b7f58a"/></linearGradient><radialGradient id="light"><stop stop-color="{GREEN}" stop-opacity=".25"/><stop offset="1" stop-color="{GREEN}" stop-opacity="0"/></radialGradient></defs>
<rect width="1200" height="365" rx="24" fill="url(#bg)"/><circle cx="1000" cy="160" r="280" fill="url(#light)"/>
<path d="M850 0h350v365H970z" fill="#16251b" opacity=".7"/><path d="M905 0v365M975 0v365M1045 0v365M1115 0v365M850 70h350M850 140h350M850 210h350M850 280h350" stroke="#39d353" stroke-opacity=".12"/>
<circle cx="196" cy="182" r="92" fill="#101b14" stroke="#39d353" stroke-width="2"/><circle cx="196" cy="182" r="76" fill="none" stroke="#39d353" stroke-opacity=".35"/><text x="196" y="195" text-anchor="middle" fill="#e6f0e8" font-family="Segoe UI,Arial,sans-serif" font-size="43" font-weight="700">ODK</text>
<text x="340" y="89" fill="#819188" font-family="Consolas,monospace" font-size="15">ORHANDOGANKAPLAN  /  GITHUB</text>
<text x="340" y="146" fill="#f0f5f1" font-family="Segoe UI,Arial,sans-serif" font-size="36" font-weight="700">{name}</text>
<text x="342" y="183" fill="#aab8ad" font-family="Segoe UI,Arial,sans-serif" font-size="19">{bio}</text>
<text x="342" y="230" fill="#55df6b" font-family="Consolas,monospace" font-size="16">&gt; build useful things. keep learning.</text>
<rect x="342" y="266" width="180" height="42" rx="10" fill="#16351d" stroke="#2c6c34"/><text x="432" y="292" text-anchor="middle" fill="#9df0a6" font-family="Consolas,monospace" font-size="14">{project_count} PROJECTS</text>
<rect x="536" y="266" width="194" height="42" rx="10" fill="#16221a" stroke="#2c4931"/><text x="633" y="292" text-anchor="middle" fill="#b2c2b4" font-family="Consolas,monospace" font-size="14">PYTHON / SYSTEMS</text>
</svg>'''


def heatmap_svg(days: list[dict[str, object]]) -> str:
    width, height, cell, gap = 1200, 230, 11, 4
    step = cell + gap
    cols = 53
    grid_width = cols * step - gap
    left = (width - grid_width) / 2
    top = 88
    first_date = date.fromisoformat(str(days[0]["date"]))
    first_sunday = first_date - timedelta(days=(first_date.weekday() + 1) % 7)
    colors = ["#161b22", "#0e4429", "#006d32", "#26a641", GREEN]
    cells: list[str] = []
    month_labels: dict[int, str] = {}
    for item in days:
        current = date.fromisoformat(str(item["date"]))
        column = (current - first_sunday).days // 7
        row = (current.weekday() + 1) % 7
        if current.day == 1:
            month_labels[column] = current.strftime("%b")
        level = max(0, min(int(item["level"]), 4))
        title = f'{current.isoformat()}: {int(item["count"])} contributions'
        cells.append(f'<rect x="{left + column * step:.1f}" y="{top + row * step}" width="{cell}" height="{cell}" rx="2" fill="{colors[level]}"><title>{esc(title)}</title></rect>')
    labels = [f'<text x="{left + col * step:.1f}" y="72" fill="{MUTED}" font-family="Segoe UI,Arial,sans-serif" font-size="12">{label}</text>' for col, label in month_labels.items()]
    total = sum(int(item["count"]) for item in days)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">GitHub contribution heatmap</title><desc id="desc">{total} contributions shown for the last year.</desc>
<rect width="{width}" height="{height}" rx="18" fill="{BG}" stroke="{BORDER}"/>
<text x="36" y="42" fill="{INK}" font-family="Consolas,monospace" font-size="14" letter-spacing="1">CONTRIBUTION HEATMAP</text><text x="1162" y="42" text-anchor="end" fill="{MUTED}" font-family="Segoe UI,Arial,sans-serif" font-size="13">{total} contributions · last year</text>
{''.join(labels)}{''.join(cells)}
<text x="938" y="202" fill="{MUTED}" font-family="Segoe UI,Arial,sans-serif" font-size="11">Less</text>{''.join(f'<rect x="{978 + i * 18}" y="192" width="11" height="11" rx="2" fill="{colors[i]}"/>' for i in range(5))}<text x="1076" y="202" fill="{MUTED}" font-family="Segoe UI,Arial,sans-serif" font-size="11">More</text>
</svg>'''


def activity_svg(days: list[dict[str, object]]) -> str:
    months = monthly_totals(days)
    values = [value for _, value in months]
    max_value = max(values, default=1) or 1
    total = sum(int(item["count"]) for item in days)
    current = current_streak(days)
    longest = longest_streak(days)
    busiest = max(months, key=lambda item: item[1]) if months else ("—", 0)
    width, height = 1200, 340
    left, base, chart_height = 82, 267, 132
    bar_width, gap = 54, 26
    chart_width = len(months) * (bar_width + gap) - gap
    start_x = (width - chart_width) / 2
    grid = []
    for fraction in (0, 0.5, 1):
        y = base - int(chart_height * fraction)
        grid.append(f'<line x1="72" y1="{y}" x2="1128" y2="{y}" stroke="#263238"/><text x="56" y="{y + 4}" text-anchor="end" fill="{FAINT}" font-family="Consolas,monospace" font-size="10">{int(max_value * fraction)}</text>')
    bars = []
    for index, (month, value) in enumerate(months):
        bar_height = max(3, int(chart_height * value / max_value)) if value else 3
        x = start_x + index * (bar_width + gap)
        y = base - bar_height
        bars.append(f'<rect x="{x:.1f}" y="{y}" width="{bar_width}" height="{bar_height}" rx="6" fill="{GREEN}" opacity="{0.48 + 0.5 * value / max_value if value else 0.22:.2f}"><title>{month}: {value} contributions</title></rect><text x="{x + bar_width / 2:.1f}" y="{base + 22}" text-anchor="middle" fill="{MUTED}" font-family="Consolas,monospace" font-size="12">{month}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Contribution activity</title><desc id="desc">{total} contributions in the last year. Current streak {current} days; longest streak {longest} days.</desc>
<rect width="{width}" height="{height}" rx="18" fill="{BG}" stroke="{BORDER}"/>
<text x="36" y="42" fill="{INK}" font-family="Consolas,monospace" font-size="14" letter-spacing="1">ACTIVITY / LAST 12 MONTHS</text>
<text x="1164" y="42" text-anchor="end" fill="{MUTED}" font-family="Segoe UI,Arial,sans-serif" font-size="13">{total} contributions</text>
<text x="82" y="76" fill="{FAINT}" font-family="Consolas,monospace" font-size="11">CURRENT STREAK  <tspan fill="{INK}">{current} DAYS</tspan></text><text x="370" y="76" fill="{FAINT}" font-family="Consolas,monospace" font-size="11">LONGEST STREAK  <tspan fill="{INK}">{longest} DAYS</tspan></text><text x="690" y="76" fill="{FAINT}" font-family="Consolas,monospace" font-size="11">BUSIEST MONTH  <tspan fill="{INK}">{busiest[0]} ({busiest[1]})</tspan></text>
{''.join(grid)}{''.join(bars)}
</svg>'''


def tile_svg(label: str, value: str, note: str, accent: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="420" height="160" viewBox="0 0 420 160" role="img" aria-labelledby="title desc">
<title id="title">{esc(label)}: {esc(value)}</title><desc id="desc">{esc(note)}</desc>
<rect x="1" y="1" width="418" height="158" rx="18" fill="{BG}" stroke="{BORDER}" stroke-width="2"/><rect x="23" y="25" width="5" height="110" rx="3" fill="{accent}"/>
<text x="46" y="50" fill="{FAINT}" font-family="Consolas,monospace" font-size="13" letter-spacing="1.2">{esc(label)}</text><text x="46" y="91" fill="{INK}" font-family="Segoe UI,Arial,sans-serif" font-size="25" font-weight="700">{esc(value)}</text><text x="46" y="121" fill="{MUTED}" font-family="Segoe UI,Arial,sans-serif" font-size="14">{esc(note)}</text>
<circle cx="380" cy="43" r="4" fill="{accent}"/><circle cx="393" cy="43" r="4" fill="{accent}" opacity=".4"/>
</svg>'''


def title_svg(dark: bool) -> str:
    bg, ink, muted, border, accent = (BG, INK, MUTED, BORDER, GREEN) if dark else ("#ffffff", "#18231b", "#59685e", "#dce5dd", "#168c2f")
    suffix = "dark" if dark else "light"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="88" viewBox="0 0 1200 88" role="img" aria-labelledby="title desc">
<title id="title">What I'm coding</title><desc id="desc">Selected coding projects.</desc>
<rect x="1" y="1" width="1198" height="86" rx="14" fill="{bg}" stroke="{border}" stroke-width="2"/><rect x="24" y="22" width="5" height="44" rx="2" fill="{accent}"/>
<text x="48" y="39" fill="{muted}" font-family="Consolas,monospace" font-size="12" letter-spacing="1.3">WHAT I'M CODING / {suffix.upper()}</text><text x="48" y="64" fill="{ink}" font-family="Segoe UI,Arial,sans-serif" font-size="22" font-weight="700">Tools that make everyday work easier</text><text x="1168" y="53" text-anchor="end" fill="{accent}" font-family="Consolas,monospace" font-size="14">PYTHON · SYSTEMS · AUTOMATION</text>
</svg>'''


def repo_svg(repo: dict[str, object], fallback: str) -> str:
    name = str(repo.get("name") or "Project")
    desc = str(repo.get("description") or fallback)
    if len(desc) > 72:
        desc = desc[:69].rstrip() + "…"
    language = str(repo.get("language") or "Open source tool")
    stars = int(repo.get("stargazers_count") or 0)
    updated = str(repo.get("updated_at") or "")[:7]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="205" viewBox="0 0 600 205" role="img" aria-labelledby="title desc">
<title id="title">{esc(name)}</title><desc id="desc">{esc(desc)}. {esc(language)}. {stars} stars.</desc>
<rect x="1" y="1" width="598" height="203" rx="18" fill="{BG}" stroke="{BORDER}" stroke-width="2"/><rect x="24" y="23" width="54" height="4" rx="2" fill="{GREEN}"/>
<text x="24" y="71" fill="{INK}" font-family="Segoe UI,Arial,sans-serif" font-size="28" font-weight="700">{esc(name)}</text><text x="24" y="106" fill="{MUTED}" font-family="Segoe UI,Arial,sans-serif" font-size="16">{esc(desc)}</text>
<line x1="24" y1="133" x2="576" y2="133" stroke="{BORDER}"/><text x="24" y="166" fill="{GREEN}" font-family="Consolas,monospace" font-size="13">{esc(language.upper())}</text><text x="576" y="166" text-anchor="end" fill="{MUTED}" font-family="Consolas,monospace" font-size="13">★ {stars}   ·   {esc(updated)}</text>
</svg>'''


def render(output: Path) -> None:
    profile, repos = fetch_profile()
    days = fetch_contributions()
    original_repos = [repo for repo in repos if repo.get("name") != USER and not repo.get("fork")]
    languages: dict[str, int] = defaultdict(int)
    for repo in original_repos:
        if repo.get("language"):
            languages[str(repo["language"])] += 1
    primary_language = max(languages, key=languages.get) if languages else "Python"
    total_stars = sum(int(repo.get("stargazers_count") or 0) for repo in original_repos)
    write_svg(output, "hero.svg", hero_svg(profile, len(original_repos)))
    write_svg(output, "heatmap.svg", heatmap_svg(days))
    write_svg(output, "activity.svg", activity_svg(days))
    write_svg(output, "build.svg", tile_svg("BUILD", f"{len(original_repos)} projects", "Public tools in progress", GREEN))
    write_svg(output, "focus.svg", tile_svg("FOCUS", f"{primary_language} + automation", f"{total_stars} stars across project repos", "#9ee66e"))
    write_svg(output, "learn.svg", tile_svg("LEARN", "Linux + networking", "Systems and cybersecurity basics", "#c4ee8b"))
    write_svg(output, "title-coding-dark.svg", title_svg(True))
    write_svg(output, "title-coding-light.svg", title_svg(False))
    selected = {
        "CursorForge": "Windows cursor customizer with 100+ styles",
        "ProcWatch": "Safe process monitoring and resource optimization",
        "NeatFlow": "Downloads organizer with smart cleanup",
    }
    repos_by_name = {str(repo.get("name")): repo for repo in original_repos}
    for name, fallback in selected.items():
        repo = repos_by_name.get(name)
        if repo:
            write_svg(output, f"repo-{name.lower()}.svg", repo_svg(repo, fallback))
    print(f"Rendered {len(list(output.glob('*.svg')))} profile cards for {USER} into {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="dist/cards", help="Directory where generated SVG cards are written")
    args = parser.parse_args()
    try:
        render(Path(args.output))
    except Exception as exc:
        print(f"Profile art generation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()