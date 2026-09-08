#!/usr/bin/env python3
# Copyright 2026 snowball
# SPDX-License-Identifier: MIT
"""Capture and verify immutable, timestamped injury-research inputs."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
import yaml
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SCHEMA_VERSION = 1
ESPN_API_ROOT = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
ESPN_NFL_INJURIES_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
)
FANTASYPROS_API_ROOT = "https://api.fantasypros.com/public/v2/json"
NFLVERSE_RELEASE_ROOT = (
    "https://github.com/nflverse/nflverse-data/releases/download"
)
ESPN_POSITION_IDS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K"}
ESPN_SLOT_IDS = [0, 2, 4, 6, 17]
ESPN_TEAM_IDS = {
    0: "FA",
    1: "ATL",
    2: "BUF",
    3: "CHI",
    4: "CIN",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GB",
    10: "TEN",
    11: "IND",
    12: "KC",
    13: "LV",
    14: "LAR",
    15: "MIA",
    16: "MIN",
    17: "NE",
    18: "NO",
    19: "NYG",
    20: "NYJ",
    21: "PHI",
    22: "ARI",
    23: "PIT",
    24: "LAC",
    25: "SF",
    26: "SEA",
    27: "TB",
    28: "WAS",
    29: "CAR",
    30: "JAX",
    33: "BAL",
    34: "HOU",
}
ESPN_NFL_TEAM_ALIASES = {"ARI": "AZ", "LAR": "LA", "WSH": "WAS"}
VINTAGES = ("pre_practice", "final_status", "inactive", "preseason", "manual")

SNAPSHOT_FIELDS = ["snapshot_id", "season", "week", "vintage", "as_of"]
PROJECTION_FIELDS = SNAPSHOT_FIELDS + [
    "source",
    "source_player_id",
    "player_name",
    "team",
    "position",
    "projection_period",
    "projected_points_ppr",
]
INJURY_FIELDS = SNAPSHOT_FIELDS + [
    "source",
    "source_player_id",
    "player_name",
    "team",
    "side",
    "role",
    "injury_type",
    "practice_1",
    "practice_2",
    "practice_3",
    "practice_status",
    "game_status",
    "probability_playing",
    "report_date",
    "source_note",
]
DEFENSIVE_CONTEXT_FIELDS = SNAPSHOT_FIELDS + [
    "source",
    "source_player_id",
    "espn_id",
    "pfr_id",
    "player_name",
    "team",
    "side",
    "role",
    "roster_position",
    "roster_status",
    "status_description_abbr",
    "depth_position",
    "depth_slot",
    "depth_rank",
    "depth_as_of",
    "prior_snap_season",
    "prior_defense_snap_share_4g",
    "prior_defense_snap_games",
]
GENERIC_PROJECTION_REQUIRED = {
    "source",
    "player_name",
    "team",
    "position",
    "projected_points_ppr",
}
GENERIC_INJURY_REQUIRED = {
    "source",
    "player_name",
    "team",
    "side",
    "role",
}


@dataclass(frozen=True)
class SnapshotSpec:
    season: int
    week: int
    vintage: str
    as_of: datetime
    captured_at: datetime
    capture_started_at: datetime | None = None


@dataclass(frozen=True)
class RawArtifact:
    source: str
    kind: str
    origin: str
    filename: str
    content: bytes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser(
        "capture", help="Create a new append-only source snapshot."
    )
    capture.add_argument("--config", type=Path, default=Path("config/league.yaml"))
    capture.add_argument("--data-dir", type=Path, default=Path("data/injury"))
    capture.add_argument("--season", type=int)
    capture.add_argument("--week", type=int, required=True)
    capture.add_argument("--vintage", choices=VINTAGES, required=True)
    capture.add_argument(
        "--as-of",
        help="Information cutoff as a timezone-aware ISO-8601 timestamp; defaults to now.",
    )
    espn_group = capture.add_mutually_exclusive_group()
    espn_group.add_argument(
        "--fetch-espn",
        action="store_true",
        help="Fetch the ESPN league player pool using credentials from .env.",
    )
    espn_group.add_argument(
        "--espn-players",
        type=Path,
        help="Import an existing raw ESPN player-pool JSON file.",
    )
    capture.add_argument(
        "--fetch-fantasypros",
        action="store_true",
        help="Fetch FantasyPros weekly projections and injuries using FANTASYPROS_API_KEY.",
    )
    capture.add_argument(
        "--fetch-espn-nfl-injuries",
        action="store_true",
        help="Fetch ESPN's public all-team NFL injury-status feed.",
    )
    capture.add_argument(
        "--fetch-nflverse",
        action="store_true",
        help="Fetch current rosters/depth charts and prior-season snap counts.",
    )
    capture.add_argument(
        "--projections-csv",
        type=Path,
        action="append",
        default=[],
        help="Import a normalized projection CSV; may be repeated.",
    )
    capture.add_argument(
        "--injuries-csv",
        type=Path,
        action="append",
        default=[],
        help="Import a normalized injury CSV; may be repeated.",
    )
    capture.add_argument(
        "--note", default="", help="Short contemporaneous note stored in the manifest."
    )

    verify = subparsers.add_parser(
        "verify", help="Verify snapshot hashes and append-only structure."
    )
    verify.add_argument("--data-dir", type=Path, default=Path("data/injury"))
    verify.add_argument(
        "--snapshot", type=Path, help="Verify one snapshot instead of the full archive."
    )

    listing = subparsers.add_parser("list", help="List captured snapshots.")
    listing.add_argument("--data-dir", type=Path, default=Path("data/injury"))
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str | None, now: datetime) -> datetime:
    if value is None:
        return now
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ValueError(f"Invalid ISO-8601 timestamp: {value}") from error
    if parsed.tzinfo is None:
        raise ValueError("The --as-of timestamp must include a UTC offset.")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now + timedelta(minutes=5):
        raise ValueError("The --as-of timestamp cannot be in the future.")
    return parsed


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp_id(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "source"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(value: Any) -> float | None:
    if value in (None, "", "NA", "null"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_league_identity(config_path: Path) -> tuple[int, str]:
    with config_path.open(encoding="utf-8") as source:
        config = yaml.safe_load(source)
    return int(config["source"]["season"]), str(config["source"]["league_id"])


def make_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET",)),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({"User-Agent": "optasy/0.1 prospective-snapshot"})
    return session


def fetch_espn_players(season: int, week: int, league_id: str) -> tuple[dict[str, Any], str]:
    load_dotenv()
    configured_league_id = os.getenv("ESPN_LEAGUE_ID", "").strip("'\"")
    swid = os.getenv("ESPN_SWID", "").strip("'\"")
    espn_s2 = os.getenv("ESPN_S2", "").strip("'\"")
    missing = [
        name
        for name, value in (("ESPN_LEAGUE_ID", configured_league_id), ("ESPN_SWID", swid), ("ESPN_S2", espn_s2))
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing ESPN credentials: {', '.join(missing)}")
    if configured_league_id != league_id:
        raise RuntimeError("ESPN_LEAGUE_ID does not match the configured league.")

    player_filter = {
        "players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
            "filterSlotIds": {"value": ESPN_SLOT_IDS},
            "filterRanksForScoringPeriodIds": {"value": [week]},
            "limit": 2000,
            "sortDraftRanks": {
                "sortPriority": 1,
                "sortAsc": True,
                "value": "PPR",
            },
        }
    }
    url = f"{ESPN_API_ROOT}/seasons/{season}/segments/0/leagues/{league_id}"
    with make_session() as session:
        session.cookies.set("SWID", swid, domain=".espn.com")
        session.cookies.set("espn_s2", espn_s2, domain=".espn.com")
        response = session.get(
            url,
            params={"view": "kona_player_info", "scoringPeriodId": week},
            headers={"x-fantasy-filter": json.dumps(player_filter)},
            timeout=60,
            allow_redirects=False,
        )
    if 300 <= response.status_code < 400:
        raise RuntimeError("Authenticated provider request returned an unexpected redirect.")
    if response.status_code in {401, 403}:
        raise RuntimeError("ESPN rejected the credentials in .env.")
    response.raise_for_status()
    payload = response.json()
    if len(payload.get("players", [])) < 200:
        raise RuntimeError("ESPN returned an unexpectedly small player pool.")
    return payload, url


def fetch_espn_nfl_injuries(season: int) -> tuple[dict[str, Any], str]:
    with make_session() as session:
        response = session.get(
            ESPN_NFL_INJURIES_URL,
            headers={"User-Agent": requests.utils.default_user_agent()},
            timeout=90,
        )
    response.raise_for_status()
    payload = response.json()
    payload_season = int(number((payload.get("season") or {}).get("year")) or 0)
    team_groups = payload.get("injuries")
    if payload_season != season:
        raise RuntimeError(
            f"ESPN NFL injury feed is for {payload_season}, not requested {season}."
        )
    if not isinstance(team_groups, list) or len(team_groups) != 32:
        raise RuntimeError(
            "ESPN NFL injury feed did not return exactly 32 team groups."
        )
    records = [
        injury
        for group in team_groups
        for injury in (group.get("injuries") or [])
        if isinstance(injury, dict)
    ]
    if len(records) < 50:
        raise RuntimeError(
            f"ESPN NFL injury feed returned only {len(records)} records."
        )
    return payload, response.url


def fantasypros_key() -> str:
    load_dotenv()
    key = os.getenv("FANTASYPROS_API_KEY", "").strip("'\"")
    if not key or "PASTE_" in key:
        raise RuntimeError("Missing FANTASYPROS_API_KEY in .env.")
    return key


def fetch_fantasypros_json(
    path: str, params: dict[str, Any], key: str
) -> tuple[dict[str, Any], str]:
    url = f"{FANTASYPROS_API_ROOT}/{path.lstrip('/')}"
    with make_session() as session:
        response = session.get(
            url,
            params=params,
            headers={"x-api-key": key},
            timeout=60,
            allow_redirects=False,
        )
    if 300 <= response.status_code < 400:
        raise RuntimeError("Authenticated provider request returned an unexpected redirect.")
    if response.status_code in {401, 403}:
        raise RuntimeError(
            "FantasyPros rejected the API key or the requested production endpoint."
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"FantasyPros returned an unexpected payload for {path}.")
    return payload, response.url


def fetch_fantasypros(
    season: int, week: int
) -> tuple[list[tuple[str, dict[str, Any], str]], dict[str, Any]]:
    key = fantasypros_key()
    positions = ("QB", "RB", "WR", "TE", "K")
    with ThreadPoolExecutor(max_workers=len(positions) + 1) as executor:
        projection_futures = {
            position: executor.submit(
                fetch_fantasypros_json,
                f"nfl/{season}/projections",
                {"position": position, "week": week},
                key,
            )
            for position in positions
        }
        injury_future = executor.submit(
            fetch_fantasypros_json,
            "nfl/injuries",
            {"year": season, "week": week, "include_probabilities": "true"},
            key,
        )
        projection_payloads = []
        for position, future in projection_futures.items():
            payload, url = future.result()
            projection_payloads.append((position, payload, url))
        injury_payload, injury_url = injury_future.result()
    return projection_payloads, {"payload": injury_payload, "url": injury_url}


def fetch_binary(url: str) -> tuple[bytes, str]:
    with make_session() as session:
        response = session.get(url, timeout=90)
    response.raise_for_status()
    content = response.content
    if len(content) < 1_000:
        raise RuntimeError(f"Source returned an unexpectedly small file: {url}")
    return content, response.url


def nflverse_urls(season: int) -> dict[str, str]:
    return {
        "rosters": f"{NFLVERSE_RELEASE_ROOT}/rosters/roster_{season}.csv.gz",
        "depth_charts": (
            f"{NFLVERSE_RELEASE_ROOT}/depth_charts/depth_charts_{season}.csv.gz"
        ),
        "snap_counts": (
            f"{NFLVERSE_RELEASE_ROOT}/snap_counts/snap_counts_{season - 1}.csv.gz"
        ),
    }


def fetch_nflverse(season: int) -> dict[str, dict[str, Any]]:
    urls = nflverse_urls(season)
    with ThreadPoolExecutor(max_workers=len(urls)) as executor:
        futures = {
            name: executor.submit(fetch_binary, url) for name, url in urls.items()
        }
        return {
            name: {
                "content": content,
                "url": final_url,
            }
            for name, future in futures.items()
            for content, final_url in [future.result()]
        }


def gzip_csv_rows(content: bytes, label: str) -> list[dict[str, str]]:
    try:
        text = gzip.decompress(content).decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RuntimeError(f"Invalid gzip CSV from {label}.") from error
    return list(csv.DictReader(io.StringIO(text)))


def defensive_role(position: str) -> str | None:
    raw = position.strip().upper()
    if raw in {"DE", "EDGE", "LDE", "RDE"}:
        return "EDGE"
    if raw in {"DT", "NT", "DI", "LDT", "RDT"}:
        return "DI"
    if raw in {"LB", "ILB", "OLB", "MLB", "WLB", "SLB", "LOLB", "ROLB"}:
        return "LB"
    if raw in {"CB", "LCB", "RCB", "NB"}:
        return "CB"
    if raw in {"S", "FS", "SS"}:
        return "S"
    if raw in {"DB", "DL"}:
        return raw
    return None


def normalize_nflverse_context(
    roster_content: bytes,
    depth_content: bytes,
    snap_content: bytes,
    season: int,
) -> list[dict[str, Any]]:
    roster_rows = gzip_csv_rows(roster_content, "nflverse rosters")
    depth_rows = gzip_csv_rows(depth_content, "nflverse depth charts")
    snap_rows = gzip_csv_rows(snap_content, "nflverse snap counts")
    if not roster_rows or not depth_rows or not snap_rows:
        raise RuntimeError("nflverse returned an empty roster, depth, or snap dataset.")

    latest_depth_timestamp = max(
        (row.get("dt") or "" for row in depth_rows), default=""
    )
    if not latest_depth_timestamp:
        raise RuntimeError("nflverse depth charts have no timestamp.")
    latest_depth: dict[str, dict[str, str]] = {}
    for row in depth_rows:
        if row.get("dt") != latest_depth_timestamp:
            continue
        player_id = row.get("gsis_id") or ""
        if not player_id or defensive_role(row.get("pos_abb") or "") is None:
            continue
        existing = latest_depth.get(player_id)
        rank = int(number(row.get("pos_rank")) or 999)
        existing_rank = int(number(existing.get("pos_rank")) or 999) if existing else 999
        if existing is None or rank < existing_rank:
            latest_depth[player_id] = row

    snap_history: dict[str, list[tuple[str, float]]] = {}
    for row in snap_rows:
        if int(number(row.get("season")) or 0) != season - 1:
            continue
        pfr_id = row.get("pfr_player_id") or ""
        defense_snaps = number(row.get("defense_snaps")) or 0
        defense_pct = number(row.get("defense_pct"))
        if not pfr_id or defense_snaps <= 0 or defense_pct is None:
            continue
        snap_history.setdefault(pfr_id, []).append(
            (row.get("game_id") or "", defense_pct)
        )

    rows: list[dict[str, Any]] = []
    seen_player_ids: set[str] = set()
    for roster in roster_rows:
        if int(number(roster.get("season")) or 0) != season:
            continue
        roster_role = defensive_role(roster.get("position") or "")
        player_id = roster.get("gsis_id") or ""
        name = (roster.get("full_name") or "").strip()
        team = (roster.get("team") or "").strip().upper()
        if roster_role is None or not player_id or not name or not team:
            continue
        if player_id in seen_player_ids:
            continue
        seen_player_ids.add(player_id)
        depth = latest_depth.get(player_id, {})
        role = defensive_role(depth.get("pos_abb") or "") or roster_role
        history = sorted(snap_history.get(roster.get("pfr_id") or "", []))[-4:]
        prior_share = (
            sum(value for _, value in history) / len(history) if history else None
        )
        rows.append(
            {
                "source": "nflverse",
                "source_player_id": player_id,
                "espn_id": roster.get("espn_id") or depth.get("espn_id") or "",
                "pfr_id": roster.get("pfr_id") or "",
                "player_name": name,
                "team": team,
                "side": "defense",
                "role": role,
                "roster_position": (roster.get("position") or "").strip().upper(),
                "roster_status": (roster.get("status") or "").strip().upper(),
                "status_description_abbr": (
                    roster.get("status_description_abbr") or ""
                ).strip(),
                "depth_position": (depth.get("pos_abb") or "").strip().upper(),
                "depth_slot": depth.get("pos_slot") or "",
                "depth_rank": depth.get("pos_rank") or "",
                "depth_as_of": latest_depth_timestamp,
                "prior_snap_season": season - 1,
                "prior_defense_snap_share_4g": (
                    "" if prior_share is None else round(prior_share, 6)
                ),
                "prior_defense_snap_games": len(history),
            }
        )
    rows.sort(
        key=lambda row: (
            row["team"],
            row["role"],
            int(number(row["depth_rank"]) or 999),
            row["player_name"],
        )
    )
    return rows


def espn_projection(
    player: dict[str, Any], season: int, scoring_period: int, split_type: int
) -> float | None:
    values = [
        number(stat.get("appliedTotal"))
        for stat in player.get("stats", [])
        if stat.get("seasonId") == season
        and stat.get("scoringPeriodId") == scoring_period
        and stat.get("statSourceId") == 1
        and stat.get("statSplitTypeId") == split_type
    ]
    return next((value for value in reversed(values) if value is not None), None)


def normalize_espn_players(
    payload: dict[str, Any], season: int, week: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    projections: list[dict[str, Any]] = []
    injuries: list[dict[str, Any]] = []
    for entry in payload.get("players", []):
        player = entry.get("player", {}) or {}
        player_id = player.get("id")
        name = str(player.get("fullName") or "").strip()
        position = ESPN_POSITION_IDS.get(player.get("defaultPositionId"))
        if not player_id or not name or position is None:
            continue
        team_id = player.get("proTeamId")
        team = ESPN_TEAM_IDS.get(team_id, str(team_id or ""))
        weekly_points = espn_projection(player, season, week, split_type=1)
        season_points = espn_projection(player, season, 0, split_type=0)
        for period, points in (("week", weekly_points), ("season", season_points)):
            if points is None:
                continue
            projections.append(
                {
                    "source": "espn_league",
                    "source_player_id": player_id,
                    "player_name": name,
                    "team": team,
                    "position": position,
                    "projection_period": period,
                    "projected_points_ppr": round(points, 6),
                }
            )

        injury_status = str(player.get("injuryStatus") or "").strip().upper()
        if player.get("injured") or injury_status not in {"", "ACTIVE", "NORMAL"}:
            injuries.append(
                {
                    "source": "espn_league",
                    "source_player_id": player_id,
                    "player_name": name,
                    "team": team,
                    "side": "special_teams" if position == "K" else "offense",
                    "role": position,
                    "injury_type": "",
                    "practice_1": "",
                    "practice_2": "",
                    "practice_3": "",
                    "practice_status": "",
                    "game_status": injury_status,
                    "probability_playing": "",
                    "report_date": "",
                    "source_note": "ESPN fantasy player status; not an official practice report",
                }
            )
    projections.sort(
        key=lambda row: (
            row["projection_period"],
            row["position"],
            -float(row["projected_points_ppr"]),
            row["player_name"],
        )
    )
    injuries.sort(key=lambda row: (row["team"], row["role"], row["player_name"]))
    return projections, injuries


def fantasypros_players(payload: dict[str, Any]) -> list[dict[str, Any]]:
    players = payload.get("players")
    if not isinstance(players, list):
        players = payload.get("player")
    return players if isinstance(players, list) else []


def fantasypros_projection_points(player: dict[str, Any]) -> float | None:
    stats = player.get("stats", {})
    candidates = stats if isinstance(stats, list) else [stats]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        points = number(candidate.get("points_ppr"))
        if points is not None:
            return points
    return None


def normalize_fantasypros_projections(
    payloads: list[tuple[str, dict[str, Any], str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for requested_position, payload, _ in payloads:
        for player in fantasypros_players(payload):
            points = fantasypros_projection_points(player)
            name = str(player.get("name") or player.get("player_name") or "").strip()
            if points is None or not name:
                continue
            rows.append(
                {
                    "source": "fantasypros",
                    "source_player_id": player.get("fpid") or player.get("player_id") or "",
                    "player_name": name,
                    "team": str(player.get("team_id") or "").strip().upper(),
                    "position": str(
                        player.get("position_id") or requested_position
                    ).strip().upper(),
                    "projection_period": "week",
                    "projected_points_ppr": round(points, 6),
                }
            )
    rows.sort(
        key=lambda row: (
            row["position"],
            -float(row["projected_points_ppr"]),
            row["player_name"],
        )
    )
    return rows


def injury_side_and_role(position: str) -> tuple[str, str]:
    raw = position.strip().upper()
    if raw in {"QB", "RB", "FB", "WR", "TE"}:
        return "offense", raw
    if raw in {"C", "G", "OG", "OT", "T", "OL"}:
        return "offense", "OL"
    if (role := defensive_role(raw)) is not None:
        return "defense", role
    if raw in {"K", "P", "LS"}:
        return "special_teams", raw
    return "unknown", raw


def espn_nfl_athlete_id(athlete: dict[str, Any]) -> str:
    for link in athlete.get("links", []):
        match = re.search(r"/id/(\d+)(?:/|$)", str(link.get("href") or ""))
        if match:
            return match.group(1)
    return ""


def normalize_espn_nfl_injuries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    team_groups = payload.get("injuries")
    if not isinstance(team_groups, list):
        raise RuntimeError("ESPN NFL injury response has no team injury groups.")
    rows: list[dict[str, Any]] = []
    for group in team_groups:
        for injury in group.get("injuries", []):
            if not isinstance(injury, dict):
                continue
            athlete = injury.get("athlete") or {}
            name = str(athlete.get("displayName") or "").strip()
            raw_position = str(
                (athlete.get("position") or {}).get("abbreviation") or ""
            ).strip().upper()
            raw_team = str(
                (athlete.get("team") or {}).get("abbreviation") or ""
            ).strip().upper()
            status = str(injury.get("status") or "").strip()
            status_key = "_".join(
                status.upper().replace("/", " ").replace("-", " ").split()
            )
            if status_key in {"", "ACTIVE", "NORMAL"}:
                continue
            if not name or not raw_position or not raw_team:
                continue
            team = ESPN_NFL_TEAM_ALIASES.get(raw_team, raw_team)
            side, role = injury_side_and_role(raw_position)
            details = injury.get("details") or {}
            rows.append(
                {
                    "source": "espn_nfl",
                    "source_player_id": espn_nfl_athlete_id(athlete),
                    "player_name": name,
                    "team": team,
                    "side": side,
                    "role": role,
                    "injury_type": str(details.get("type") or "").strip(),
                    "practice_1": "",
                    "practice_2": "",
                    "practice_3": "",
                    "practice_status": "",
                    "game_status": status,
                    "probability_playing": "",
                    "report_date": str(injury.get("date") or "").strip(),
                    "source_note": (
                        "ESPN public all-team injury status; not an official "
                        f"practice/game report; injury_record_id={injury.get('id') or ''}"
                    ),
                }
            )
    rows.sort(key=lambda row: (row["team"], row["side"], row["role"], row["player_name"]))
    return rows


def normalize_fantasypros_injuries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    source_rows = payload.get("injuries")
    if not isinstance(source_rows, list):
        raise RuntimeError("FantasyPros injury response has no injuries list.")
    rows: list[dict[str, Any]] = []
    for injury in source_rows:
        if not isinstance(injury, dict):
            continue
        name = str(injury.get("name") or injury.get("player_name") or "").strip()
        raw_position = str(injury.get("position_id") or "").strip().upper()
        if not name or not raw_position:
            continue
        probability = number(injury.get("probability_of_playing"))
        if probability is not None and not 0 <= probability <= 1:
            probability = None
        side, role = injury_side_and_role(raw_position)
        practices = [
            str(injury.get(f"practice_{day}") or "").strip()
            for day in (1, 2, 3)
        ]
        latest_practice = next(
            (practice for practice in reversed(practices) if practice), ""
        )
        notes = [f"raw_position={raw_position}"]
        if injury.get("status_short"):
            notes.append(f"status_short={injury['status_short']}")
        rows.append(
            {
                "source": "fantasypros",
                "source_player_id": injury.get("player_id") or injury.get("fpid") or "",
                "player_name": name,
                "team": str(injury.get("team_id") or "").strip().upper(),
                "side": side,
                "role": role,
                "injury_type": str(
                    injury.get("practice_report_injury_type")
                    or injury.get("injury_type")
                    or ""
                ).strip(),
                "practice_1": practices[0],
                "practice_2": practices[1],
                "practice_3": practices[2],
                "practice_status": latest_practice,
                "game_status": str(injury.get("status") or "").strip(),
                "probability_playing": (
                    "" if probability is None else round(probability, 6)
                ),
                "report_date": str(injury.get("injury_update_date") or "").strip(),
                "source_note": "; ".join(notes),
            }
        )
    rows.sort(key=lambda row: (row["team"], row["side"], row["role"], row["player_name"]))
    return rows


def require_columns(path: Path, fieldnames: list[str] | None, required: set[str]) -> None:
    missing = sorted(required - set(fieldnames or []))
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")


def read_generic_projections(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        require_columns(path, reader.fieldnames, GENERIC_PROJECTION_REQUIRED)
        rows = []
        for line_number, row in enumerate(reader, start=2):
            points = number(row.get("projected_points_ppr"))
            if points is None:
                raise ValueError(
                    f"{path}:{line_number} has invalid projected_points_ppr."
                )
            rows.append(
                {
                    "source": row["source"].strip(),
                    "source_player_id": row.get("source_player_id", "").strip(),
                    "player_name": row["player_name"].strip(),
                    "team": row["team"].strip().upper(),
                    "position": row["position"].strip().upper(),
                    "projection_period": (
                        row.get("projection_period", "week").strip() or "week"
                    ),
                    "projected_points_ppr": round(points, 6),
                }
            )
    if any(
        not row["source"]
        or not row["player_name"]
        or not row["team"]
        or not row["position"]
        for row in rows
    ):
        raise ValueError(
            f"{path} contains a blank source, player_name, team, or position."
        )
    return rows


def read_generic_injuries(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        require_columns(path, reader.fieldnames, GENERIC_INJURY_REQUIRED)
        rows = []
        for line_number, row in enumerate(reader, start=2):
            probability = number(row.get("probability_playing"))
            if probability is not None and not 0 <= probability <= 1:
                raise ValueError(
                    f"{path}:{line_number} probability_playing must be in [0, 1]."
                )
            rows.append(
                {
                    "source": row["source"].strip(),
                    "source_player_id": row.get("source_player_id", "").strip(),
                    "player_name": row["player_name"].strip(),
                    "team": row["team"].strip().upper(),
                    "side": row["side"].strip().lower(),
                    "role": row["role"].strip().upper(),
                    "injury_type": row.get("injury_type", "").strip(),
                    "practice_1": row.get("practice_1", "").strip(),
                    "practice_2": row.get("practice_2", "").strip(),
                    "practice_3": row.get("practice_3", "").strip(),
                    "practice_status": row.get("practice_status", "").strip(),
                    "game_status": row.get("game_status", "").strip(),
                    "probability_playing": (
                        "" if probability is None else round(probability, 6)
                    ),
                    "report_date": row.get("report_date", "").strip(),
                    "source_note": row.get("source_note", "").strip(),
                }
            )
    if any(
        not row["source"]
        or not row["player_name"]
        or not row["team"]
        or not row["side"]
        or not row["role"]
        for row in rows
    ):
        raise ValueError(
            f"{path} contains a blank source, player_name, team, side, or role."
        )
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> int:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def with_snapshot_metadata(
    rows: Iterable[dict[str, Any]], spec: SnapshotSpec, snapshot_id: str
) -> list[dict[str, Any]]:
    metadata = {
        "snapshot_id": snapshot_id,
        "season": spec.season,
        "week": spec.week,
        "vintage": spec.vintage,
        "as_of": isoformat(spec.as_of),
    }
    return [{**metadata, **row} for row in rows]


def file_record(root: Path, path: Path, *, kind: str, rows: int | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": kind,
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if rows is not None:
        record["rows"] = rows
    return record


def build_snapshot(
    data_dir: Path,
    spec: SnapshotSpec,
    artifacts: list[RawArtifact],
    projections: list[dict[str, Any]],
    injuries: list[dict[str, Any]],
    defensive_context: list[dict[str, Any]] | None = None,
    *,
    note: str = "",
) -> Path:
    defensive_context = defensive_context or []
    if not artifacts:
        raise ValueError("A snapshot requires at least one raw source artifact.")
    if spec.vintage not in VINTAGES:
        raise ValueError(f"Unknown snapshot vintage: {spec.vintage}")
    if not 1 <= spec.week <= 22:
        raise ValueError("Week must be between 1 and 22.")
    if spec.as_of > spec.captured_at + timedelta(minutes=5):
        raise ValueError("Snapshot information cutoff cannot be in the future.")

    snapshot_id = (
        f"{spec.season}-w{spec.week:02d}-{slug(spec.vintage)}-"
        f"{timestamp_id(spec.captured_at)}"
    )
    parent = data_dir / "snapshots" / str(spec.season) / f"week-{spec.week:02d}"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / snapshot_id
    if destination.exists():
        raise FileExistsError(f"Snapshot already exists and cannot be overwritten: {destination}")

    staging = Path(tempfile.mkdtemp(prefix=f".{snapshot_id}-", dir=parent))
    try:
        source_records = []
        declared_files = []
        for index, artifact in enumerate(artifacts, start=1):
            suffix = Path(artifact.filename).suffix.lower()
            if suffix not in {".json", ".csv", ".txt", ".gz"}:
                suffix = ".bin"
            raw_path = (
                staging
                / "raw"
                / f"{index:02d}-{slug(artifact.source)}-{slug(artifact.kind)}{suffix}"
            )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            with raw_path.open("xb") as output:
                output.write(artifact.content)
            record = file_record(staging, raw_path, kind="raw")
            record.update(
                {
                    "source": artifact.source,
                    "source_kind": artifact.kind,
                    "origin": artifact.origin,
                }
            )
            source_records.append(record)
            declared_files.append(record)

        projection_path = staging / "normalized" / "projections.csv"
        injury_path = staging / "normalized" / "injuries.csv"
        context_path = staging / "normalized" / "defensive-context.csv"
        projection_count = write_csv(
            projection_path,
            PROJECTION_FIELDS,
            with_snapshot_metadata(projections, spec, snapshot_id),
        )
        injury_count = write_csv(
            injury_path,
            INJURY_FIELDS,
            with_snapshot_metadata(injuries, spec, snapshot_id),
        )
        context_count = write_csv(
            context_path,
            DEFENSIVE_CONTEXT_FIELDS,
            with_snapshot_metadata(defensive_context, spec, snapshot_id),
        )
        projection_record = file_record(
            staging, projection_path, kind="normalized_projections", rows=projection_count
        )
        injury_record = file_record(
            staging, injury_path, kind="normalized_injuries", rows=injury_count
        )
        context_record = file_record(
            staging,
            context_path,
            kind="normalized_defensive_context",
            rows=context_count,
        )
        declared_files.extend((projection_record, injury_record, context_record))

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "season": spec.season,
            "week": spec.week,
            "vintage": spec.vintage,
            "as_of": isoformat(spec.as_of),
            "capture_started_at": isoformat(
                spec.capture_started_at or spec.captured_at
            ),
            "captured_at": isoformat(spec.captured_at),
            "capture_mode": "live" if any(item.origin.startswith("https://") for item in artifacts) else "imported",
            "note": note,
            "information_policy": (
                "Only information available at or before as_of is eligible for this vintage; "
                "later vintages and outcomes are forbidden inputs."
            ),
            "sources": source_records,
            "files": declared_files,
            "counts": {
                "projections": projection_count,
                "injuries": injury_count,
                "defensive_context": context_count,
                "projections_by_source": dict(
                    sorted(Counter(str(row.get("source") or "") for row in projections).items())
                ),
                "injuries_by_source": dict(
                    sorted(Counter(str(row.get("source") or "") for row in injuries).items())
                ),
                "defensive_context_by_source": dict(
                    sorted(
                        Counter(
                            str(row.get("source") or "")
                            for row in defensive_context
                        ).items()
                    )
                ),
            },
        }
        manifest_path = staging / "manifest.json"
        with manifest_path.open("x", encoding="utf-8") as output:
            json.dump(manifest, output, indent=2, sort_keys=True)
            output.write("\n")
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


def safe_snapshot_file(snapshot_dir: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe manifest path: {relative_path}")
    resolved = (snapshot_dir / candidate).resolve()
    if snapshot_dir.resolve() not in resolved.parents:
        raise ValueError(f"Manifest path escapes snapshot: {relative_path}")
    return resolved


def verify_snapshot(snapshot_dir: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        return [f"missing manifest: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"invalid manifest {manifest_path}: {error}"]
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported schema version in {manifest_path}")
    if manifest.get("snapshot_id") != snapshot_dir.name:
        errors.append(f"snapshot ID does not match directory: {snapshot_dir}")

    declared = {"manifest.json"}
    for record in manifest.get("files", []):
        relative_path = str(record.get("path") or "")
        try:
            path = safe_snapshot_file(snapshot_dir, relative_path)
        except ValueError as error:
            errors.append(str(error))
            continue
        declared.add(relative_path)
        if not path.is_file():
            errors.append(f"missing declared file: {path}")
            continue
        if path.stat().st_size != record.get("bytes"):
            errors.append(f"byte count mismatch: {path}")
        if sha256_file(path) != record.get("sha256"):
            errors.append(f"sha256 mismatch: {path}")

    actual = {
        path.relative_to(snapshot_dir).as_posix()
        for path in snapshot_dir.rglob("*")
        if path.is_file()
    }
    extras = sorted(actual - declared)
    missing_declarations = sorted(declared - actual)
    if extras:
        errors.append(f"undeclared files in {snapshot_dir}: {', '.join(extras)}")
    if missing_declarations:
        errors.append(
            f"declared files absent in {snapshot_dir}: {', '.join(missing_declarations)}"
        )
    return errors


def manifest_paths(data_dir: Path) -> list[Path]:
    return sorted((data_dir / "snapshots").glob("*/week-*/*/manifest.json"))


def capture(args: argparse.Namespace) -> Path:
    configured_season, league_id = load_league_identity(args.config)
    season = args.season or configured_season
    if season != configured_season and (
        args.fetch_espn or args.fetch_espn_nfl_injuries
    ):
        raise ValueError("Live ESPN capture season must match config/league.yaml.")
    live_capture = (
        args.fetch_espn
        or args.fetch_espn_nfl_injuries
        or args.fetch_fantasypros
        or args.fetch_nflverse
    )
    if live_capture and args.as_of:
        raise ValueError(
            "Live captures set --as-of when retrieval finishes; do not backdate them."
        )
    capture_started_at = utc_now()

    artifacts: list[RawArtifact] = []
    projections: list[dict[str, Any]] = []
    injuries: list[dict[str, Any]] = []
    defensive_context: list[dict[str, Any]] = []
    if args.fetch_espn:
        payload, origin = fetch_espn_players(season, args.week, league_id)
        content = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
        artifacts.append(
            RawArtifact("espn_league", "player_pool", origin, "espn-players.json", content)
        )
        espn_projections, espn_injuries = normalize_espn_players(
            payload, season, args.week
        )
        projections.extend(espn_projections)
        injuries.extend(espn_injuries)
    elif args.espn_players:
        content = args.espn_players.read_bytes()
        payload = json.loads(content)
        artifacts.append(
            RawArtifact(
                "espn_league",
                "player_pool",
                str(args.espn_players.resolve()),
                args.espn_players.name,
                content,
            )
        )
        espn_projections, espn_injuries = normalize_espn_players(
            payload, season, args.week
        )
        projections.extend(espn_projections)
        injuries.extend(espn_injuries)

    if args.fetch_espn_nfl_injuries:
        payload, origin = fetch_espn_nfl_injuries(season)
        content = (
            json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode()
        artifacts.append(
            RawArtifact(
                "espn_nfl",
                "league_injuries",
                origin,
                "espn-nfl-injuries.json",
                content,
            )
        )
        espn_nfl_injuries = normalize_espn_nfl_injuries(payload)
        defensive_records = [
            row for row in espn_nfl_injuries if row["side"] == "defense"
        ]
        if len(defensive_records) < 10:
            raise RuntimeError(
                "ESPN NFL feed produced only "
                f"{len(defensive_records)} non-active defensive injury records."
            )
        injuries.extend(espn_nfl_injuries)

    if args.fetch_fantasypros:
        projection_payloads, injury_result = fetch_fantasypros(season, args.week)
        limited_responses = [
            position
            for position, payload, _ in projection_payloads
            if payload.get("public_api_limited")
        ]
        if injury_result["payload"].get("public_api_limited"):
            limited_responses.append("injuries")
        if limited_responses:
            raise RuntimeError(
                "FantasyPros API access is sample-limited for: "
                f"{', '.join(limited_responses)}. Activate a personal production "
                "key before using this source prospectively."
            )
        for position, payload, origin in projection_payloads:
            content = (
                json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
            ).encode()
            artifacts.append(
                RawArtifact(
                    "fantasypros",
                    f"{position.lower()}_projections",
                    origin,
                    f"fantasypros-{position.lower()}-projections.json",
                    content,
                )
            )
        injury_content = (
            json.dumps(
                injury_result["payload"], separators=(",", ":"), sort_keys=True
            )
            + "\n"
        ).encode()
        artifacts.append(
            RawArtifact(
                "fantasypros",
                "injuries",
                injury_result["url"],
                "fantasypros-injuries.json",
                injury_content,
            )
        )
        fantasypros_projections = normalize_fantasypros_projections(
            projection_payloads
        )
        if len(fantasypros_projections) < 100:
            raise RuntimeError(
                "FantasyPros returned only "
                f"{len(fantasypros_projections)} usable weekly projections."
            )
        projections.extend(fantasypros_projections)
        injuries.extend(
            normalize_fantasypros_injuries(injury_result["payload"])
        )

    if args.fetch_nflverse:
        nflverse = fetch_nflverse(season)
        for source_kind, result in nflverse.items():
            artifacts.append(
                RawArtifact(
                    "nflverse",
                    source_kind,
                    result["url"],
                    f"nflverse-{source_kind}.csv.gz",
                    result["content"],
                )
            )
        nflverse_context = normalize_nflverse_context(
            nflverse["rosters"]["content"],
            nflverse["depth_charts"]["content"],
            nflverse["snap_counts"]["content"],
            season,
        )
        if len(nflverse_context) < 400:
            raise RuntimeError(
                f"nflverse produced only {len(nflverse_context)} defensive records."
            )
        defensive_context.extend(nflverse_context)

    for path in args.projections_csv:
        content = path.read_bytes()
        artifacts.append(
            RawArtifact("normalized_import", "projections", str(path.resolve()), path.name, content)
        )
        projections.extend(read_generic_projections(path))
    for path in args.injuries_csv:
        content = path.read_bytes()
        artifacts.append(
            RawArtifact("normalized_import", "injuries", str(path.resolve()), path.name, content)
        )
        injuries.extend(read_generic_injuries(path))

    captured_at = utc_now()
    as_of = captured_at if live_capture else parse_timestamp(args.as_of, captured_at)
    spec = SnapshotSpec(
        season=season,
        week=args.week,
        vintage=args.vintage,
        as_of=as_of,
        captured_at=captured_at,
        capture_started_at=capture_started_at,
    )

    destination = build_snapshot(
        args.data_dir,
        spec,
        artifacts,
        projections,
        injuries,
        defensive_context,
        note=args.note,
    )
    return destination


def main() -> int:
    args = parse_args()
    try:
        if args.command == "capture":
            destination = capture(args)
            manifest = json.loads((destination / "manifest.json").read_text())
            print(
                f"[captured] {manifest['snapshot_id']} "
                f"projections={manifest['counts']['projections']} "
                f"injuries={manifest['counts']['injuries']} "
                f"defenders={manifest['counts'].get('defensive_context', 0)}"
            )
            print(destination)
            return 0
        if args.command == "verify":
            snapshot_dirs = (
                [args.snapshot]
                if args.snapshot
                else [path.parent for path in manifest_paths(args.data_dir)]
            )
            if not snapshot_dirs:
                raise RuntimeError("No snapshots found to verify.")
            errors = [
                error
                for snapshot_dir in snapshot_dirs
                for error in verify_snapshot(snapshot_dir)
            ]
            if errors:
                for error in errors:
                    print(f"[invalid] {error}", file=sys.stderr)
                return 1
            print(f"[verified] snapshots={len(snapshot_dirs)}")
            return 0
        if args.command == "list":
            paths = manifest_paths(args.data_dir)
            for path in paths:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                print(
                    f"{manifest['snapshot_id']}  as_of={manifest['as_of']}  "
                    f"projections={manifest['counts']['projections']}  "
                    f"injuries={manifest['counts']['injuries']}  "
                    f"defenders={manifest['counts'].get('defensive_context', 0)}"
                )
            print(f"snapshots={len(paths)}")
            return 0
    except (OSError, RuntimeError, ValueError, requests.RequestException) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
