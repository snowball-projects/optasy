#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Refresh, build, and watch Optasy's minimal 2026 draft board."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
import yaml
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ESPN_API_ROOT = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
DYNASTYPROCESS_ROOT = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/files"
)
RANKINGS_URL = f"{DYNASTYPROCESS_ROOT}/db_fpecr_latest.csv"
PLAYER_IDS_URL = f"{DYNASTYPROCESS_ROOT}/db_playerids.csv"
CALIBRATION_RANKINGS = {
    2024: {
        "sha": "d60ce28b9b3ff306bcafb61976d578fed193b469",
        "scrape_date": "2024-08-30",
    },
    2025: {
        "sha": "3db9c5fbd519e8f26103d5c24ad2824dfc8c88d6",
        "scrape_date": "2025-08-29",
    },
}
CALIBRATION_CONSENSUS_CUTOFF = 60
POSITION_SHRINKAGE_PRIOR = 20
AVAILABILITY_BETA_PRIOR = 1
OPENING_DECISION_COUNT = 3
OPENING_CANDIDATE_LIMIT = 10
MIN_CANDIDATE_AVAILABILITY = 0.05
LIKELY_NEXT_PICK_AVAILABILITY = 0.5

ESPN_POSITION_IDS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K"}
ESPN_SLOT_IDS = [0, 2, 4, 6, 17]
BOARD_FIELDS = [
    "available",
    "consensus_rank",
    "player",
    "team",
    "position",
    "position_rank",
    "expert_average_rank",
    "espn_adp",
    "adp_minus_ecr",
    "espn_ppr_rank",
    "espn_rank_minus_ecr",
    "espn_projected_points",
    "replacement_rank",
    "replacement_points",
    "value_over_replacement",
    "expert_best_rank",
    "expert_worst_rank",
    "expert_rank_sd",
    "expert_rank_range",
    "espn_average_auction_value",
    "espn_rank_auction_value",
    "injury_status",
    "injured",
    "last_news_at",
    "percent_owned",
    "bye_week",
    "espn_id",
    "fantasypros_id",
    "match_method",
    "drafted_overall",
    "drafted_by_team_id",
    "consensus_as_of",
    "snapshot_at",
]
OPENING_DECISION_FIELDS = [
    "decision_pick",
    "roster_before_pick",
    "candidate_order",
    "player",
    "team",
    "position",
    "candidate_type",
    "selection_posture",
    "consensus_rank",
    "expert_average_rank",
    "espn_adp",
    "estimated_pick_median",
    "estimated_pick_p25",
    "estimated_pick_p75",
    "availability_at_pick_pct",
    "next_user_pick",
    "availability_at_next_pick_pct",
    "next_pick_complementary_option",
    "next_pick_option_position",
    "next_pick_option_consensus_rank",
    "next_pick_option_availability_pct",
    "projected_points",
    "replacement_rank",
    "replacement_points",
    "value_over_replacement",
    "next_pick_option_projected_points",
    "next_pick_option_value_over_replacement",
    "two_pick_planning_value",
    "likely_same_position_next_option",
    "likely_same_position_next_vorp",
    "value_lost_if_waiting",
    "expert_rank_sd",
    "injury_status",
    "opponent_signal_before_next_pick",
    "why_in_pool",
    "consensus_as_of",
    "calibration_seasons",
    "availability_method",
    "rankings_source_url",
    "espn_source_url",
]
LIVE_RANKING_FIELDS = [
    "decision_rank",
    "eligible_for_recommendation",
    "player",
    "team",
    "position",
    "roster_fit",
    "roster_position_count",
    "position_maximum",
    "espn_projected_points",
    "value_over_replacement",
    "replacement_rank",
    "replacement_points",
    "consensus_rank",
    "espn_ppr_rank",
    "espn_adp",
    "availability_at_next_user_pick_pct",
    "availability_conditioning_samples",
    "expert_rank_sd",
    "injury_status",
    "injured",
    "last_news_at",
    "policy_review",
    "espn_id",
    "snapshot_at",
]
SOURCE_CHANGE_FIELDS = [
    "review_priority",
    "review_reasons",
    "player",
    "position",
    "team",
    "espn_id",
    "change_types",
    "previous_injury_status",
    "current_injury_status",
    "previous_injured",
    "current_injured",
    "previous_last_news_at",
    "current_last_news_at",
    "previous_projected_points",
    "current_projected_points",
    "projected_points_change",
    "previous_value_over_replacement",
    "current_value_over_replacement",
    "value_over_replacement_change",
    "previous_consensus_rank",
    "current_consensus_rank",
    "consensus_rank_change",
    "previous_espn_ppr_rank",
    "current_espn_ppr_rank",
    "espn_ppr_rank_change",
    "previous_espn_adp",
    "current_espn_adp",
    "espn_adp_change",
    "previous_snapshot",
    "current_snapshot",
]


@dataclass(frozen=True)
class LeagueContext:
    season: int
    league_id: str
    team_count: int
    user_pick_position: int
    draft_rounds: int
    allowed_positions: frozenset[str]
    starter_counts: tuple[tuple[str, int], ...]
    flex_count: int
    position_maximums: tuple[tuple[str, int], ...] = ()
    lineup_counts: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class CalibrationSample:
    season: int
    position: str
    consensus_rank: int
    actual_pick: int
    residual: int


@dataclass(frozen=True)
class EspnCredentials:
    league_id: str
    swid: str
    espn_s2: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=("refresh", "build", "freeze-sources", "watch"),
        default="refresh",
    )
    parser.add_argument("--config", type=Path, default=Path("config/league.yaml"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/draft"))
    parser.add_argument(
        "--snapshot",
        help="Snapshot directory or ID; defaults to the newest snapshot.",
    )
    parser.add_argument(
        "--refresh-reference",
        action="store_true",
        help="Redownload the occasionally changing player-ID crosswalk.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Seconds between ESPN draft checks in watch mode.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Check ESPN once in watch mode, then exit (useful for testing).",
    )
    parser.add_argument(
        "--amendment-reason",
        help=(
            "Required to append a new frozen source version after an initial "
            "freeze; intended only for material late-breaking news."
        ),
    )
    return parser.parse_args()


def load_context(config_path: Path) -> LeagueContext:
    with config_path.open(encoding="utf-8") as source:
        config = yaml.safe_load(source)
    source_config = config["source"]
    lineup_slots = config["roster"]["lineup_slots"]
    positions = {
        position.replace("D_ST", "D/ST")
        for position, count in lineup_slots.items()
        if count > 0
    }
    positions.discard("D/ST")
    positions.discard("FLEX")
    return LeagueContext(
        season=int(source_config["season"]),
        league_id=str(source_config["league_id"]),
        team_count=int(config["league"]["team_count"]),
        user_pick_position=int(config["draft"]["user_pick_position"]),
        draft_rounds=int(config["roster"]["roster_size"]),
        allowed_positions=frozenset(positions),
        starter_counts=tuple(
            (position, int(lineup_slots.get(position, 0)))
            for position in ("QB", "RB", "WR", "TE")
        ),
        flex_count=int(lineup_slots.get("FLEX", 0)),
        position_maximums=tuple(
            (
                position.replace("D_ST", "D/ST"),
                int(maximum),
            )
            for position, maximum in config["roster"]["positional_maximums"].items()
        ),
        lineup_counts=tuple(
            (position, int(lineup_slots.get(position, 0)))
            for position in ("QB", "RB", "WR", "TE", "K")
        ),
    )


def load_credentials(context: LeagueContext) -> EspnCredentials:
    load_dotenv()
    values = {
        "league_id": os.getenv("ESPN_LEAGUE_ID", "").strip("'\""),
        "swid": os.getenv("ESPN_SWID", "").strip("'\""),
        "espn_s2": os.getenv("ESPN_S2", "").strip("'\""),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Missing ESPN credentials: {', '.join(missing)}")
    if values["league_id"] != context.league_id:
        raise RuntimeError("ESPN_LEAGUE_ID does not match config/league.yaml.")
    return EspnCredentials(**values)


def make_session(credentials: EspnCredentials | None = None) -> requests.Session:
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
    session.headers.update({"User-Agent": "optasy/0.1 draft-board"})
    if credentials:
        session.cookies.set("SWID", credentials.swid, domain=".espn.com")
        session.cookies.set("espn_s2", credentials.espn_s2, domain=".espn.com")
    return session


def espn_league_url(context: LeagueContext) -> str:
    return (
        f"{ESPN_API_ROOT}/seasons/{context.season}/segments/0/leagues/"
        f"{context.league_id}"
    )


def fetch_espn_players(
    context: LeagueContext, credentials: EspnCredentials
) -> dict[str, Any]:
    player_filter = {
        "players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
            "filterSlotIds": {"value": ESPN_SLOT_IDS},
            "filterRanksForScoringPeriodIds": {"value": [0]},
            "limit": 2000,
            "sortDraftRanks": {
                "sortPriority": 1,
                "sortAsc": True,
                "value": "PPR",
            },
        }
    }
    with make_session(credentials) as session:
        response = session.get(
            espn_league_url(context),
            params={"view": "kona_player_info", "scoringPeriodId": 0},
            headers={"x-fantasy-filter": json.dumps(player_filter)},
            timeout=60,
        )
    if response.status_code in {401, 403}:
        raise RuntimeError("ESPN rejected the credentials in .env.")
    response.raise_for_status()
    payload = response.json()
    if len(payload.get("players", [])) < 200:
        raise RuntimeError("ESPN returned an unexpectedly small player pool.")
    return payload


def fetch_espn_draft(
    context: LeagueContext, credentials: EspnCredentials
) -> dict[str, Any]:
    with make_session(credentials) as session:
        response = session.get(
            espn_league_url(context),
            params=[("view", "mDraftDetail"), ("view", "mStatus")],
            timeout=45,
        )
    if response.status_code in {401, 403}:
        raise RuntimeError("ESPN rejected the credentials in .env.")
    response.raise_for_status()
    payload = response.json()
    if str(payload.get("id")) != context.league_id:
        raise RuntimeError("ESPN returned an unexpected league.")
    return payload


def download_text(url: str) -> str:
    with make_session() as session:
        response = session.get(url, timeout=60)
    response.raise_for_status()
    return response.text


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(path)


def write_json(path: Path, payload: Any) -> None:
    write_text(
        path,
        json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
    )


def publish_draft_snapshot(
    destination: Path,
    espn_players: dict[str, Any],
    espn_draft: dict[str, Any],
    rankings_text: str,
    manifest: dict[str, Any],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    destination_created = False
    try:
        write_json(staging / "espn-players.json", espn_players)
        write_json(staging / "espn-draft.json", espn_draft)
        write_text(staging / "dynastyprocess-rankings.csv", rankings_text)
        write_json(staging / "manifest.json", manifest)
        try:
            destination.mkdir()
        except FileExistsError as error:
            raise FileExistsError(
                "Draft snapshot already exists and cannot be overwritten: "
                f"{destination}"
            ) from error
        destination_created = True
        for filename in (
            "espn-players.json",
            "espn-draft.json",
            "dynastyprocess-rankings.csv",
            "manifest.json",
        ):
            (staging / filename).replace(destination / filename)
        staging.rmdir()
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if destination_created:
            shutil.rmtree(destination, ignore_errors=True)
        raise


def write_csv(
    path: Path,
    rows: Iterable[dict[str, Any]],
    fieldnames: list[str] = BOARD_FIELDS,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)


def snapshot_timestamp() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ"), now.isoformat()


def reference_path(data_dir: Path) -> Path:
    return data_dir / "reference" / "dynastyprocess-player-ids.csv"


def calibration_rankings_url(season: int) -> str:
    sha = CALIBRATION_RANKINGS[season]["sha"]
    return (
        "https://raw.githubusercontent.com/dynastyprocess/data/"
        f"{sha}/files/db_fpecr_latest.csv"
    )


def calibration_path(data_dir: Path, season: int) -> Path:
    return data_dir / "reference" / f"dynastyprocess-rankings-{season}.csv"


def refresh_reference(data_dir: Path, force: bool) -> Path:
    path = reference_path(data_dir)
    if path.exists() and not force:
        print(f"[reference cached] {path}", flush=True)
        return path
    text = download_text(PLAYER_IDS_URL)
    row_count = sum(1 for _ in csv.DictReader(io.StringIO(text)))
    if row_count < 5_000:
        raise RuntimeError("DynastyProcess returned an unexpectedly small ID crosswalk.")
    write_text(path, text)
    print(f"[reference refreshed] rows={row_count} {path}", flush=True)
    return path


def ensure_calibration_references(data_dir: Path) -> dict[int, Path]:
    paths = {}
    for season in sorted(CALIBRATION_RANKINGS):
        path = calibration_path(data_dir, season)
        paths[season] = path
        if path.exists():
            continue
        text = download_text(calibration_rankings_url(season))
        rows = list(csv.DictReader(io.StringIO(text)))
        expected_date = CALIBRATION_RANKINGS[season]["scrape_date"]
        if len(rows) < 1_000 or not any(
            row.get("scrape_date") == expected_date for row in rows
        ):
            raise RuntimeError(
                f"Unexpected DynastyProcess calibration snapshot for {season}."
            )
        write_text(path, text)
        print(f"[calibration cached] season={season} rows={len(rows)}", flush=True)
    return paths


def refresh(
    context: LeagueContext,
    credentials: EspnCredentials,
    data_dir: Path,
    force_reference: bool,
) -> Path:
    id_path = refresh_reference(data_dir, force_reference)
    ensure_calibration_references(data_dir)
    with ThreadPoolExecutor(max_workers=3) as executor:
        players_future = executor.submit(fetch_espn_players, context, credentials)
        draft_future = executor.submit(fetch_espn_draft, context, credentials)
        rankings_future = executor.submit(download_text, RANKINGS_URL)
        espn_players = players_future.result()
        espn_draft = draft_future.result()
        rankings_text = rankings_future.result()

    ranking_rows = list(csv.DictReader(io.StringIO(rankings_text)))
    ppr_rows = [
        row
        for row in ranking_rows
        if row.get("page_type") == "redraft-overall"
        and row.get("fp_page") == "/nfl/rankings/ppr-cheatsheets.php"
    ]
    if len(ppr_rows) < 200:
        raise RuntimeError("DynastyProcess returned an unexpectedly small PPR ranking set.")

    snapshot_id, captured_at = snapshot_timestamp()
    snapshot_dir = data_dir / "snapshots" / snapshot_id
    manifest = {
        "captured_at": captured_at,
        "season": context.season,
        "league_id": context.league_id,
        "espn_player_count": len(espn_players.get("players", [])),
        "dynastyprocess_total_rows": len(ranking_rows),
        "dynastyprocess_ppr_overall_rows": len(ppr_rows),
        "dynastyprocess_consensus_as_of": ppr_rows[0].get("scrape_date"),
        "reference_path": str(id_path),
        "sources": {
            "espn": espn_league_url(context),
            "dynastyprocess_rankings": RANKINGS_URL,
            "dynastyprocess_player_ids": PLAYER_IDS_URL,
        },
    }
    publish_draft_snapshot(
        snapshot_dir,
        espn_players,
        espn_draft,
        rankings_text,
        manifest,
    )
    print(
        f"[snapshot] ESPN players={len(espn_players.get('players', []))}, "
        f"PPR consensus={len(ppr_rows)} {snapshot_dir}",
        flush=True,
    )
    return snapshot_dir


def resolve_snapshot(data_dir: Path, requested: str | None) -> Path:
    if requested:
        candidate = Path(requested)
        if not candidate.exists():
            candidate = data_dir / "snapshots" / requested
        if not candidate.is_dir():
            raise RuntimeError(f"Snapshot not found: {requested}")
        return candidate
    snapshots_root = data_dir / "snapshots"
    candidates = sorted(
        path
        for path in snapshots_root.glob("*")
        if path.is_dir() and (path / "manifest.json").exists()
    )
    if not candidates:
        raise RuntimeError("No draft snapshots found. Run the refresh command first.")
    return candidates[-1]


def previous_snapshot(data_dir: Path, current: Path) -> Path | None:
    candidates = sorted(
        path
        for path in (data_dir / "snapshots").glob("*")
        if path.is_dir() and (path / "manifest.json").exists()
    )
    current_resolved = current.resolve()
    for index, candidate in enumerate(candidates):
        if candidate.resolve() == current_resolved:
            return candidates[index - 1] if index > 0 else None
    return None


def build_source_changes(
    previous_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
    previous_snapshot_id: str,
    current_snapshot_id: str,
) -> list[dict[str, Any]]:
    """Diff source vintages without assigning unvalidated news sentiment."""
    previous_by_id = {int(row["espn_id"]): row for row in previous_rows}
    current_by_id = {int(row["espn_id"]): row for row in current_rows}
    changes = []

    def delta(current: Any, previous: Any) -> int | float | str:
        current_number = number(current)
        previous_number = number(previous)
        if current_number is None or previous_number is None:
            return ""
        return rounded(current_number - previous_number)

    for espn_id in sorted(previous_by_id.keys() | current_by_id.keys()):
        previous = previous_by_id.get(espn_id, {})
        current = current_by_id.get(espn_id, {})
        change_types = []
        if not previous:
            change_types.append("player_added")
        if not current:
            change_types.append("player_removed")
        compared_fields = (
            ("injury_status", "injury_status"),
            ("injured", "injured_flag"),
            ("last_news_at", "new_player_news_timestamp"),
            ("espn_projected_points", "projection"),
            ("value_over_replacement", "value_over_replacement"),
            ("consensus_rank", "consensus_rank"),
            ("espn_ppr_rank", "espn_ppr_rank"),
            ("espn_adp", "espn_adp"),
        )
        for field, label in compared_fields:
            if previous.get(field, "") != current.get(field, ""):
                change_types.append(label)
        if not change_types:
            continue

        reasons = []
        if any(
            change in change_types for change in ("injury_status", "injured_flag")
        ):
            reasons.append("injury_state_changed")
        if "new_player_news_timestamp" in change_types:
            reasons.append("espn_news_timestamp_changed")
        projection_change = delta(
            current.get("espn_projected_points"),
            previous.get("espn_projected_points"),
        )
        vorp_change = delta(
            current.get("value_over_replacement"),
            previous.get("value_over_replacement"),
        )
        consensus_change = delta(
            current.get("consensus_rank"), previous.get("consensus_rank")
        )
        espn_rank_change = delta(
            current.get("espn_ppr_rank"), previous.get("espn_ppr_rank")
        )
        if any(
            isinstance(value, (int, float)) and abs(value) >= threshold
            for value, threshold in (
                (projection_change, 10),
                (vorp_change, 10),
                (consensus_change, 5),
                (espn_rank_change, 5),
            )
        ):
            reasons.append("material_numeric_input_change")
        if "player_removed" in change_types:
            reasons.append("player_removed_from_active_pool")

        if "injury_state_changed" in reasons:
            priority = "1_injury_review"
        elif "player_removed_from_active_pool" in reasons:
            priority = "1_removed_player_review"
        elif "espn_news_timestamp_changed" in reasons:
            priority = "2_news_review"
        elif "material_numeric_input_change" in reasons:
            priority = "3_material_input_review"
        else:
            priority = "4_routine_source_update"
        basis = current or previous
        changes.append(
            {
                "review_priority": priority,
                "review_reasons": ";".join(reasons) or "routine_source_update",
                "player": basis.get("player", ""),
                "position": basis.get("position", ""),
                "team": basis.get("team", ""),
                "espn_id": espn_id,
                "change_types": ";".join(change_types),
                "previous_injury_status": previous.get("injury_status", ""),
                "current_injury_status": current.get("injury_status", ""),
                "previous_injured": previous.get("injured", ""),
                "current_injured": current.get("injured", ""),
                "previous_last_news_at": previous.get("last_news_at", ""),
                "current_last_news_at": current.get("last_news_at", ""),
                "previous_projected_points": previous.get(
                    "espn_projected_points", ""
                ),
                "current_projected_points": current.get(
                    "espn_projected_points", ""
                ),
                "projected_points_change": projection_change,
                "previous_value_over_replacement": previous.get(
                    "value_over_replacement", ""
                ),
                "current_value_over_replacement": current.get(
                    "value_over_replacement", ""
                ),
                "value_over_replacement_change": vorp_change,
                "previous_consensus_rank": previous.get("consensus_rank", ""),
                "current_consensus_rank": current.get("consensus_rank", ""),
                "consensus_rank_change": consensus_change,
                "previous_espn_ppr_rank": previous.get("espn_ppr_rank", ""),
                "current_espn_ppr_rank": current.get("espn_ppr_rank", ""),
                "espn_ppr_rank_change": espn_rank_change,
                "previous_espn_adp": previous.get("espn_adp", ""),
                "current_espn_adp": current.get("espn_adp", ""),
                "espn_adp_change": delta(
                    current.get("espn_adp"), previous.get("espn_adp")
                ),
                "previous_snapshot": previous_snapshot_id,
                "current_snapshot": current_snapshot_id,
            }
        )
    changes.sort(
        key=lambda row: (
            row["review_priority"],
            integer(row.get("current_consensus_rank")) or sys.maxsize,
            row["player"],
        )
    )
    return changes


def frozen_source_paths(data_dir: Path, season: int) -> list[Path]:
    return sorted((data_dir / "frozen" / str(season)).glob("baseline-*.json"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_draft_sources(
    context: LeagueContext,
    data_dir: Path,
    snapshot_dir: Path,
    config_path: Path,
    amendment_reason: str | None = None,
) -> Path:
    """Freeze one source vintage without claiming the human policy is final."""
    existing = frozen_source_paths(data_dir, context.season)
    if not existing and (amendment_reason or "").strip():
        raise RuntimeError(
            "--amendment-reason is only valid after an initial source freeze."
        )
    if existing and not (amendment_reason or "").strip():
        raise RuntimeError(
            "A frozen draft source baseline already exists. Supply a material "
            "--amendment-reason to append a new version; the original is immutable."
        )
    version = len(existing) + 1
    destination = (
        data_dir
        / "frozen"
        / str(context.season)
        / f"baseline-{version:03d}-{snapshot_dir.name}.json"
    )
    manifest_path = snapshot_dir / "manifest.json"
    manifest = read_json(manifest_path)
    if int(manifest.get("season", 0)) != context.season:
        raise RuntimeError("Draft snapshot season does not match league configuration.")
    if str(manifest.get("league_id")) != context.league_id:
        raise RuntimeError("Draft snapshot league does not match league configuration.")
    source_files = (
        "manifest.json",
        "espn-players.json",
        "espn-draft.json",
        "dynastyprocess-rankings.csv",
    )
    source_hashes = {
        filename: file_sha256(snapshot_dir / filename) for filename in source_files
    }
    payload = {
        "schema_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "season": context.season,
        "league_id": context.league_id,
        "snapshot_id": snapshot_dir.name,
        "snapshot_captured_at": manifest.get("captured_at"),
        "snapshot_files_sha256": source_hashes,
        "baseline_version": version,
        "amendment_reason": (amendment_reason or "").strip() or None,
        "previous_baseline_path": str(existing[-1]) if existing else None,
        "previous_baseline_sha256": (
            file_sha256(existing[-1]) if existing else None
        ),
        "draft_board_code_sha256": file_sha256(Path(__file__)),
        "league_config_path": str(config_path),
        "league_config_sha256": file_sha256(config_path),
        "decision_protocol_path": "reports/2026-draft-decision-protocol.md",
        "decision_protocol_sha256": file_sha256(
            Path("reports/2026-draft-decision-protocol.md")
        ),
        "policy_status": (
            "source_inputs_frozen; human decision thresholds remain separately gated"
        ),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
    return destination


def resolve_frozen_draft_sources(
    context: LeagueContext,
    data_dir: Path,
    config_path: Path,
) -> Path:
    baselines = frozen_source_paths(data_dir, context.season)
    if not baselines:
        raise RuntimeError(
            "No frozen draft source baseline. Run freeze-sources after the final "
            "pre-draft refresh, or pass --snapshot for an explicit dry run."
        )
    for index, path in enumerate(baselines):
        record = read_json(path)
        if integer(record.get("baseline_version")) != index + 1:
            raise RuntimeError("Frozen draft source versions are not contiguous.")
        if index == 0:
            if record.get("previous_baseline_path") is not None:
                raise RuntimeError("Initial frozen draft source has an invalid parent.")
            continue
        previous = baselines[index - 1]
        if (
            Path(str(record.get("previous_baseline_path"))) != previous
            or record.get("previous_baseline_sha256") != file_sha256(previous)
        ):
            raise RuntimeError("Frozen draft source amendment chain is invalid.")
    baseline_path = baselines[-1]
    baseline = read_json(baseline_path)
    snapshot_dir = data_dir / "snapshots" / str(baseline["snapshot_id"])
    checks = {
        "draft_board_code_sha256": file_sha256(Path(__file__)),
        "league_config_sha256": file_sha256(config_path),
        "decision_protocol_sha256": file_sha256(
            Path(str(baseline["decision_protocol_path"]))
        ),
    }
    for field, actual in checks.items():
        if baseline.get(field) != actual:
            raise RuntimeError(
                f"Frozen draft baseline verification failed for {field}."
            )
    for filename, expected in baseline["snapshot_files_sha256"].items():
        path = snapshot_dir / filename
        if not path.exists() or file_sha256(path) != expected:
            raise RuntimeError(f"Frozen draft source verification failed: {path}")
    return snapshot_dir


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def integer(value: Any) -> int | None:
    if value in (None, "", "NA"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def number(value: Any) -> float | None:
    if value in (None, "", "NA"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rounded(value: float | None) -> int | float | str:
    if value is None:
        return ""
    result = round(value, 2)
    return int(result) if result.is_integer() else result


def timestamp_millis(value: Any) -> str:
    timestamp = number(value)
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat()


def canonical_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return "".join(character for character in normalized.lower() if character.isalnum())


def season_projection(player: dict[str, Any], season: int) -> float | None:
    projections = [
        stat.get("appliedTotal")
        for stat in player.get("stats", [])
        if stat.get("seasonId") == season
        and stat.get("statSourceId") == 1
        and stat.get("statSplitTypeId") == 0
    ]
    values = [number(value) for value in projections]
    return next((value for value in reversed(values) if value is not None), None)


def draft_picks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        pick
        for pick in payload.get("draftDetail", {}).get("picks", []) or []
        if (player_id := integer(pick.get("playerId"))) is not None and player_id > 0
    ]


def user_pick_sequence(context: LeagueContext) -> list[int]:
    picks = []
    for round_number in range(1, context.draft_rounds + 1):
        slot = (
            context.user_pick_position
            if round_number % 2 == 1
            else context.team_count - context.user_pick_position + 1
        )
        picks.append((round_number - 1) * context.team_count + slot)
    return picks


def draft_slots(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every scheduled slot, including ESPN's unfilled playerId=-1 rows."""
    return sorted(
        payload.get("draftDetail", {}).get("picks", []) or [],
        key=lambda pick: integer(pick.get("overallPickNumber")) or sys.maxsize,
    )


def draft_state_sha256(payload: dict[str, Any]) -> str:
    """Fingerprint selections and slot ownership so pick trades trigger rebuilds."""
    state = [
        {
            "overall_pick": integer(pick.get("overallPickNumber")),
            "player_id": integer(pick.get("playerId")),
            "team_id": integer(pick.get("teamId")),
        }
        for pick in draft_slots(payload)
    ]
    return hashlib.sha256(
        json.dumps(state, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def infer_user_team_id(
    context: LeagueContext, draft_payload: dict[str, Any]
) -> int:
    """Resolve the user's ESPN team ID from the configured original draft slot."""
    pick_order = (
        draft_payload.get("settings", {})
        .get("draftSettings", {})
        .get("pickOrder", [])
        or []
    )
    if len(pick_order) >= context.user_pick_position:
        team_id = integer(pick_order[context.user_pick_position - 1])
        if team_id is not None:
            return team_id

    first_pick = next(
        (
            pick
            for pick in draft_slots(draft_payload)
            if integer(pick.get("overallPickNumber")) == context.user_pick_position
        ),
        None,
    )
    team_id = integer(first_pick.get("teamId")) if first_pick else None
    if team_id is None:
        raise RuntimeError("Could not infer the user's ESPN team ID from draft state.")
    return team_id


def user_draft_state(
    context: LeagueContext, draft_payload: dict[str, Any]
) -> dict[str, Any]:
    """Resolve traded slots and whether the user is currently on the clock."""
    user_team_id = infer_user_team_id(context, draft_payload)
    slots = draft_slots(draft_payload)
    completed = [
        pick
        for pick in slots
        if (player_id := integer(pick.get("playerId"))) is not None and player_id > 0
    ]
    last_overall_pick = max(
        (
            integer(pick.get("overallPickNumber")) or 0
            for pick in completed
        ),
        default=0,
    )
    remaining_user_picks = [
        integer(pick.get("overallPickNumber"))
        for pick in slots
        if integer(pick.get("teamId")) == user_team_id
        and (integer(pick.get("playerId")) or -1) <= 0
        and integer(pick.get("overallPickNumber")) is not None
    ]
    next_user_pick = min(remaining_user_picks, default=None)
    picks_until_user_turn = (
        max(0, next_user_pick - last_overall_pick - 1)
        if next_user_pick is not None
        else None
    )
    return {
        "user_team_id": user_team_id,
        "last_overall_pick": last_overall_pick,
        "next_user_pick": next_user_pick,
        "upcoming_user_picks": sorted(remaining_user_picks),
        "picks_until_user_turn": picks_until_user_turn,
        "on_clock": next_user_pick == last_overall_pick + 1,
    }


def load_calibration_samples(
    context: LeagueContext,
    data_dir: Path,
    database_path: Path,
) -> list[CalibrationSample]:
    """Join immutable pre-draft ranks to this league's realized draft positions."""
    if not database_path.exists():
        raise RuntimeError(
            f"Historical database missing: {database_path}. Run the history exporter."
        )
    id_rows = read_csv_rows(reference_path(data_dir))
    fp_to_espn = {
        fp_id: espn_id
        for row in id_rows
        if (fp_id := integer(row.get("fantasypros_id"))) is not None
        and (espn_id := integer(row.get("espn_id"))) is not None
    }
    database_uri = f"file:{database_path.resolve()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        actual_picks = {
            (int(season), int(player_id)): int(overall_pick)
            for season, player_id, overall_pick in connection.execute(
                "SELECT season, player_id, overall_pick FROM draft_picks"
            )
        }

    samples: list[CalibrationSample] = []
    for season, metadata in sorted(CALIBRATION_RANKINGS.items()):
        path = calibration_path(data_dir, season)
        if not path.exists():
            raise RuntimeError(
                f"Calibration reference missing for {season}. Run refresh first."
            )
        rankings = [
            row
            for row in read_csv_rows(path)
            if row.get("page_type") == "redraft-overall"
            and row.get("fp_page") == "/nfl/rankings/ppr-cheatsheets.php"
            and row.get("pos") in context.allowed_positions
        ]
        rankings.sort(key=lambda row: number(row.get("ecr")) or float("inf"))
        relevant = rankings[:CALIBRATION_CONSENSUS_CUTOFF]
        dates = {row.get("scrape_date") for row in relevant}
        if dates != {metadata["scrape_date"]}:
            raise RuntimeError(
                f"Unexpected relevant calibration dates for {season}: {sorted(dates)}"
            )
        season_samples = []
        for consensus_rank, ranking in enumerate(relevant, start=1):
            fp_id = integer(ranking.get("id"))
            espn_id = fp_to_espn.get(fp_id) if fp_id is not None else None
            actual_pick = actual_picks.get((season, espn_id)) if espn_id else None
            if actual_pick is None:
                continue
            season_samples.append(
                CalibrationSample(
                    season=season,
                    position=ranking["pos"],
                    consensus_rank=consensus_rank,
                    actual_pick=actual_pick,
                    residual=actual_pick - consensus_rank,
                )
            )
        if len(season_samples) < 55:
            raise RuntimeError(
                f"Only {len(season_samples)}/60 calibration players matched in {season}."
            )
        samples.extend(season_samples)
    return samples


def weighted_quantile(
    values_and_weights: Iterable[tuple[float, float]], quantile: float
) -> float:
    if not 0 <= quantile <= 1:
        raise ValueError("Quantile must be between zero and one.")
    ordered = sorted(values_and_weights)
    total_weight = sum(weight for _, weight in ordered)
    if total_weight <= 0:
        raise ValueError("Weighted quantile requires positive total weight.")
    threshold = quantile * total_weight
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def availability_estimate(
    consensus_rank: int,
    target_pick: int,
    position: str,
    samples: list[CalibrationSample],
) -> dict[str, float]:
    """Estimate draft position with a small-sample position/global blend."""
    global_samples = samples
    position_samples = [sample for sample in samples if sample.position == position]
    if not global_samples:
        raise ValueError("Availability estimation requires calibration samples.")

    threshold = target_pick - consensus_rank
    prior = AVAILABILITY_BETA_PRIOR

    def smoothed_probability(group: list[CalibrationSample]) -> float:
        successes = sum(sample.residual >= threshold for sample in group)
        return (successes + prior) / (len(group) + 2 * prior)

    global_probability = smoothed_probability(global_samples)
    if position_samples:
        position_probability = smoothed_probability(position_samples)
        position_weight = len(position_samples) / (
            len(position_samples) + POSITION_SHRINKAGE_PRIOR
        )
    else:
        position_probability = global_probability
        position_weight = 0.0
    probability = (
        position_weight * position_probability
        + (1 - position_weight) * global_probability
    )

    distribution: list[tuple[float, float]] = []
    global_weight = (1 - position_weight) / len(global_samples)
    distribution.extend(
        (sample.residual, global_weight) for sample in global_samples
    )
    if position_samples:
        specific_weight = position_weight / len(position_samples)
        distribution.extend(
            (sample.residual, specific_weight) for sample in position_samples
        )

    return {
        "availability": probability,
        "pick_p25": max(
            1, consensus_rank + weighted_quantile(distribution, 0.25)
        ),
        "pick_median": max(
            1, consensus_rank + weighted_quantile(distribution, 0.5)
        ),
        "pick_p75": max(
            1, consensus_rank + weighted_quantile(distribution, 0.75)
        ),
        "position_weight": position_weight,
    }


def conditional_availability_estimate(
    consensus_rank: int,
    observed_through_pick: int,
    target_pick: int,
    position: str,
    samples: list[CalibrationSample],
) -> dict[str, float | int]:
    """Estimate survival to a future pick conditional on the observed board."""
    if observed_through_pick <= 0:
        unconditional = availability_estimate(
            consensus_rank, target_pick, position, samples
        )
        return {
            "availability": unconditional["availability"],
            "conditioning_samples": len(samples),
        }
    if target_pick <= observed_through_pick + 1:
        return {"availability": 1.0, "conditioning_samples": len(samples)}
    survived_threshold = observed_through_pick + 1 - consensus_rank
    target_threshold = target_pick - consensus_rank
    survivors = [
        sample for sample in samples if sample.residual >= survived_threshold
    ]
    if not survivors:
        return {"availability": 0.0, "conditioning_samples": 0}
    position_survivors = [
        sample for sample in survivors if sample.position == position
    ]
    prior = AVAILABILITY_BETA_PRIOR

    def smoothed_probability(group: list[CalibrationSample]) -> float:
        successes = sum(sample.residual >= target_threshold for sample in group)
        return (successes + prior) / (len(group) + 2 * prior)

    global_probability = smoothed_probability(survivors)
    if position_survivors:
        position_probability = smoothed_probability(position_survivors)
        position_weight = len(position_survivors) / (
            len(position_survivors) + POSITION_SHRINKAGE_PRIOR
        )
    else:
        position_probability = global_probability
        position_weight = 0.0
    return {
        "availability": (
            position_weight * position_probability
            + (1 - position_weight) * global_probability
        ),
        "conditioning_samples": len(survivors),
    }


def _candidate_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "player": row["player"],
        "position": row["position"],
        "espn_id": integer(row.get("espn_id")),
        "projected_points": number(row.get("espn_projected_points")),
        "value_over_replacement": number(row.get("value_over_replacement")),
        "consensus_rank": integer(row.get("consensus_rank")),
        "espn_ppr_rank": integer(row.get("espn_ppr_rank")),
        "injury_status": row.get("injury_status", ""),
        "last_news_at": row.get("last_news_at", ""),
        "roster_fit": row.get("roster_fit"),
        "policy_review": row.get("policy_review"),
        "availability_at_next_user_pick_pct": number(
            row.get("availability_at_next_user_pick_pct")
        ),
    }


def build_live_rankings(
    context: LeagueContext,
    rows: list[dict[str, Any]],
    samples: list[CalibrationSample],
    draft_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rank the actual remaining board and disclose roster/policy constraints."""
    state = user_draft_state(context, draft_payload)
    user_team_id = state["user_team_id"]
    roster = [
        row
        for row in rows
        if integer(row.get("drafted_by_team_id")) == user_team_id
        and integer(row.get("drafted_overall")) is not None
    ]
    roster_counts = {
        position: sum(row["position"] == position for row in roster)
        for position in context.allowed_positions
    }
    starter_counts = dict(context.starter_counts)
    lineup_counts = dict(context.lineup_counts or context.starter_counts)
    position_maximums = dict(context.position_maximums)
    flex_positions = {"RB", "WR", "TE"}
    flex_used = sum(
        max(0, roster_counts.get(position, 0) - starter_counts.get(position, 0))
        for position in flex_positions
    )
    flex_unfilled = max(0, context.flex_count - flex_used)
    next_pick = state["next_user_pick"]
    required_missing = {
        position: max(0, count - roster_counts.get(position, 0))
        for position, count in lineup_counts.items()
    }
    missing_required_slots = sum(required_missing.values()) + flex_unfilled
    remaining_roster_slots = len(state["upcoming_user_picks"])
    required_lineup_deadline = (
        missing_required_slots > 0
        and remaining_roster_slots <= missing_required_slots
    )

    live_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("available") != "yes":
            continue
        position = row["position"]
        position_count = roster_counts.get(position, 0)
        position_maximum = position_maximums.get(position, context.draft_rounds)
        within_maximum = position_count < position_maximum
        vorp = number(row.get("value_over_replacement"))
        fills_required_slot = (
            required_missing.get(position, 0) > 0
            or (position in flex_positions and flex_unfilled > 0)
        )
        eligible = within_maximum and vorp is not None
        if required_lineup_deadline:
            eligible = within_maximum and fills_required_slot

        if position_count < lineup_counts.get(position, 0):
            roster_fit = "fills_direct_starter"
        elif position in flex_positions and flex_unfilled > 0:
            roster_fit = "fills_flex"
        else:
            roster_fit = "adds_depth"

        policy_reviews = []
        if not within_maximum:
            policy_reviews.append("position_maximum_reached")
        if required_lineup_deadline and not fills_required_slot:
            policy_reviews.append("required_lineup_slot_deadline")
        if required_lineup_deadline and fills_required_slot and vorp is None:
            policy_reviews.append("required_starter_fallback_without_projection")
        if position in {"QB", "TE"} and position_count > 0:
            policy_reviews.append("duplicate_qb_te_requires_depth_review")
        if (
            position in {"QB", "TE"}
            and next_pick is not None
            and next_pick <= context.team_count * OPENING_DECISION_COUNT
        ):
            policy_reviews.append("early_qb_te_exception_threshold_unfrozen")
        if (
            position == "K"
            and next_pick is not None
            and next_pick <= context.team_count * 10
        ):
            policy_reviews.append("early_kicker_review")
        injury_status = str(row.get("injury_status", "")).upper()
        if row.get("injured") == "yes" or injury_status not in {
            "",
            "ACTIVE",
            "NORMAL",
        }:
            policy_reviews.append("current_injury_requires_human_review")

        consensus_rank = integer(row.get("consensus_rank"))
        availability_conditioning_samples: int | str = ""
        if state["on_clock"]:
            availability_pct: float | str = 100.0
            availability_conditioning_samples = len(samples)
        elif (
            consensus_rank is not None
            and consensus_rank <= CALIBRATION_CONSENSUS_CUTOFF
            and next_pick is not None
        ):
            availability = conditional_availability_estimate(
                consensus_rank,
                state["last_overall_pick"],
                next_pick,
                position,
                samples,
            )
            availability_pct = rounded(100 * availability["availability"])
            availability_conditioning_samples = int(
                availability["conditioning_samples"]
            )
        else:
            availability_pct = ""

        live_rows.append(
            {
                "decision_rank": "",
                "eligible_for_recommendation": "yes" if eligible else "no",
                "player": row["player"],
                "team": row["team"],
                "position": position,
                "roster_fit": roster_fit,
                "roster_position_count": position_count,
                "position_maximum": position_maximum,
                "espn_projected_points": row["espn_projected_points"],
                "value_over_replacement": row["value_over_replacement"],
                "replacement_rank": row["replacement_rank"],
                "replacement_points": row["replacement_points"],
                "consensus_rank": row["consensus_rank"],
                "espn_ppr_rank": row["espn_ppr_rank"],
                "espn_adp": row["espn_adp"],
                "availability_at_next_user_pick_pct": availability_pct,
                "availability_conditioning_samples": (
                    availability_conditioning_samples
                ),
                "expert_rank_sd": row["expert_rank_sd"],
                "injury_status": row["injury_status"],
                "injured": row["injured"],
                "last_news_at": row.get("last_news_at", ""),
                "policy_review": ";".join(policy_reviews) or "none",
                "espn_id": row["espn_id"],
                "snapshot_at": row["snapshot_at"],
            }
        )

    def live_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        vorp = number(row.get("value_over_replacement"))
        return (
            row["eligible_for_recommendation"] != "yes",
            row["roster_fit"] != "fills_direct_starter"
            if required_lineup_deadline
            else False,
            -(vorp if vorp is not None else -float("inf")),
            integer(row.get("consensus_rank")) or sys.maxsize,
            integer(row.get("espn_ppr_rank")) or sys.maxsize,
        )

    live_rows.sort(key=live_sort_key)
    ranked = [
        row
        for row in live_rows
        if row["eligible_for_recommendation"] == "yes"
    ]
    for rank, row in enumerate(ranked, start=1):
        row["decision_rank"] = rank

    def lowest_rank(field: str) -> dict[str, Any] | None:
        candidates = [row for row in live_rows if integer(row.get(field)) is not None]
        return min(candidates, key=lambda row: int(row[field]), default=None)

    def highest_vorp(
        candidates: Iterable[dict[str, Any]],
    ) -> dict[str, Any] | None:
        scored = [
            row
            for row in candidates
            if number(row.get("value_over_replacement")) is not None
        ]
        return max(
            scored,
            key=lambda row: (
                float(row["value_over_replacement"]),
                -(integer(row.get("consensus_rank")) or sys.maxsize),
            ),
            default=None,
        )

    rb_wr_candidates = [
        row
        for row in ranked
        if row["position"] in {"RB", "WR"}
    ]
    recommendation = ranked[0] if ranked else None
    strongest_alternative = ranked[1] if len(ranked) > 1 else None
    if next_pick is None:
        status = "draft_complete_for_user"
    elif state["on_clock"]:
        status = "on_clock"
    else:
        status = "contingent_waiting_for_prior_picks"
    recommendation_record = {
        **state,
        "status": status,
        "roster": [_candidate_summary(row) for row in roster],
        "roster_counts": roster_counts,
        "recommendation": _candidate_summary(recommendation),
        "strongest_alternative": _candidate_summary(strongest_alternative),
        "baseline_recommendations": {
            "fantasypros_consensus": _candidate_summary(lowest_rank("consensus_rank")),
            "espn_ppr_rank": _candidate_summary(lowest_rank("espn_ppr_rank")),
            "highest_projected_vorp": _candidate_summary(highest_vorp(live_rows)),
            "early_rb_wr_policy": _candidate_summary(highest_vorp(rb_wr_candidates)),
        },
        "ordering_rule": (
            "Highest frozen ESPN projected value over league replacement among "
            "available players within roster position maximums; consensus rank "
            "breaks ties. Roster fit, injury, and policy reviews are disclosed, "
            "not hidden in an unvalidated composite score."
        ),
        "reversal_conditions": [
            "Material player news after the frozen source snapshot.",
            "The unresolved early-QB/TE exception threshold changes the policy choice.",
            "A practical-equivalence band permits scarcity evidence to break a near tie.",
        ],
        "opponent_injury_signal": (
            "shadow_only_not_in_draft_order_until_prospectively_validated"
        ),
        "policy_status": "provisional_until_draft_protocol_is_frozen",
    }
    return live_rows, recommendation_record


def starter_replacement_levels(
    context: LeagueContext, rows: list[dict[str, Any]]
) -> dict[str, dict[str, float | int]]:
    """Find marginal projected starters after allocating the league's FLEX slots."""
    projections = [
        (projected, row)
        for row in rows
        if row["position"] in {"QB", "RB", "WR", "TE"}
        and (projected := number(row.get("espn_projected_points"))) is not None
    ]
    selected: list[tuple[float, dict[str, Any]]] = []
    for position, count in context.starter_counts:
        position_players = sorted(
            (item for item in projections if item[1]["position"] == position),
            key=lambda item: item[0],
            reverse=True,
        )
        selected.extend(position_players[: context.team_count * count])

    selected_ids = {str(row["espn_id"]) for _, row in selected}
    flex_players = sorted(
        (
            item
            for item in projections
            if item[1]["position"] in {"RB", "WR", "TE"}
            and str(item[1]["espn_id"]) not in selected_ids
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    selected.extend(flex_players[: context.team_count * context.flex_count])

    levels: dict[str, dict[str, float | int]] = {}
    for position, count in context.starter_counts:
        if count <= 0:
            continue
        position_points = [
            projected for projected, row in selected if row["position"] == position
        ]
        if not position_points:
            raise RuntimeError(f"No projected starters found at {position}.")
        levels[position] = {
            "rank": len(position_points),
            "points": min(position_points),
        }
    return levels


def likely_next_pick_option(
    rows: list[dict[str, Any]],
    target_pick: int,
    samples: list[CalibrationSample],
    excluded_espn_id: int,
    positions: set[str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, float] | None]:
    candidates = []
    for row in rows:
        if integer(row.get("espn_id")) == excluded_espn_id:
            continue
        if row.get("available") != "yes" or row.get("position") not in {
            "QB",
            "RB",
            "WR",
            "TE",
        }:
            continue
        if positions is not None and row["position"] not in positions:
            continue
        rank = integer(row.get("consensus_rank"))
        vorp = number(row.get("value_over_replacement"))
        if rank is None or rank > CALIBRATION_CONSENSUS_CUTOFF or vorp is None:
            continue
        estimate = availability_estimate(rank, target_pick, row["position"], samples)
        if estimate["availability"] >= LIKELY_NEXT_PICK_AVAILABILITY:
            candidates.append((vorp, -rank, row, estimate))
    if not candidates:
        return None, None
    _, _, option, estimate = max(candidates, key=lambda item: (item[0], item[1]))
    return option, estimate


def build_opening_decision_rows(
    context: LeagueContext,
    rows: list[dict[str, Any]],
    samples: list[CalibrationSample],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build a compact conditional recommendation table for the opening picks."""
    all_user_picks = user_pick_sequence(context)
    decisions: list[dict[str, Any]] = []
    for pick_index, decision_pick in enumerate(
        all_user_picks[:OPENING_DECISION_COUNT]
    ):
        next_pick = all_user_picks[pick_index + 1]
        prior_user_picks = set(all_user_picks[:pick_index])
        prior_positions = [
            row["position"]
            for row in rows
            if integer(row.get("drafted_overall")) in prior_user_picks
        ]
        candidates = []
        for row in rows:
            rank = integer(row.get("consensus_rank"))
            vorp = number(row.get("value_over_replacement"))
            if (
                row.get("available") != "yes"
                or row.get("position") not in {"QB", "RB", "WR", "TE"}
                or rank is None
                or rank > CALIBRATION_CONSENSUS_CUTOFF
                or vorp is None
            ):
                continue
            if (
                row["position"] in {"QB", "TE"}
                and row["position"] in prior_positions
            ):
                continue
            at_pick = availability_estimate(
                rank, decision_pick, row["position"], samples
            )
            if at_pick["availability"] < MIN_CANDIDATE_AVAILABILITY:
                continue
            candidates.append((vorp, -rank, row, at_pick))
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        likely_candidates = [
            item
            for item in candidates
            if item[3]["availability"] >= 0.2
        ][: OPENING_CANDIDATE_LIMIT - 2]
        unlikely_falls = [
            item
            for item in candidates
            if item[3]["availability"] < 0.2
        ][:2]
        candidates = sorted(
            likely_candidates + unlikely_falls,
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )

        for candidate_order, (_, _, row, at_pick) in enumerate(candidates, start=1):
            rank = int(row["consensus_rank"])
            espn_id = int(row["espn_id"])
            at_next = availability_estimate(
                rank, next_pick, row["position"], samples
            )
            complementary, complementary_estimate = likely_next_pick_option(
                rows, next_pick, samples, espn_id
            )
            same_position, same_position_estimate = likely_next_pick_option(
                rows,
                next_pick,
                samples,
                espn_id,
                positions={row["position"]},
            )
            vorp = number(row.get("value_over_replacement")) or 0.0
            complementary_vorp = (
                number(complementary.get("value_over_replacement"))
                if complementary
                else None
            )
            same_position_vorp = (
                number(same_position.get("value_over_replacement"))
                if same_position
                else None
            )
            if row["position"] in {"QB", "TE"}:
                candidate_type = "policy_exception_check"
            elif (
                at_pick["availability"] < 0.2
                and rank <= decision_pick - 6
            ):
                candidate_type = "unlikely_fall"
            else:
                candidate_type = "primary_rb_wr_pool"

            if row["position"] in {"QB", "TE"}:
                posture = "requires_exception_review"
            elif candidate_order == 1:
                posture = "preferred_by_primary_objective"
            elif candidate_order <= 3:
                posture = "strongest_alternative"
            else:
                posture = "consider_if_available"

            wait_cost = (
                vorp - same_position_vorp
                if same_position_vorp is not None
                else None
            )
            decisions.append(
                {
                    "decision_pick": decision_pick,
                    "roster_before_pick": (
                        "-".join(prior_positions) if prior_positions else "not_yet_observed"
                    ),
                    "candidate_order": candidate_order,
                    "player": row["player"],
                    "team": row["team"],
                    "position": row["position"],
                    "candidate_type": candidate_type,
                    "selection_posture": posture,
                    "consensus_rank": rank,
                    "expert_average_rank": row["expert_average_rank"],
                    "espn_adp": row["espn_adp"],
                    "estimated_pick_median": rounded(at_pick["pick_median"]),
                    "estimated_pick_p25": rounded(at_pick["pick_p25"]),
                    "estimated_pick_p75": rounded(at_pick["pick_p75"]),
                    "availability_at_pick_pct": rounded(
                        100 * at_pick["availability"]
                    ),
                    "next_user_pick": next_pick,
                    "availability_at_next_pick_pct": rounded(
                        100 * at_next["availability"]
                    ),
                    "next_pick_complementary_option": (
                        complementary["player"] if complementary else ""
                    ),
                    "next_pick_option_position": (
                        complementary["position"] if complementary else ""
                    ),
                    "next_pick_option_consensus_rank": (
                        complementary["consensus_rank"] if complementary else ""
                    ),
                    "next_pick_option_availability_pct": rounded(
                        100 * complementary_estimate["availability"]
                        if complementary_estimate
                        else None
                    ),
                    "projected_points": row["espn_projected_points"],
                    "replacement_rank": row["replacement_rank"],
                    "replacement_points": row["replacement_points"],
                    "value_over_replacement": row["value_over_replacement"],
                    "next_pick_option_projected_points": (
                        complementary["espn_projected_points"]
                        if complementary
                        else ""
                    ),
                    "next_pick_option_value_over_replacement": rounded(
                        complementary_vorp
                    ),
                    "two_pick_planning_value": rounded(
                        vorp + complementary_vorp
                        if complementary_vorp is not None
                        else None
                    ),
                    "likely_same_position_next_option": (
                        same_position["player"] if same_position else ""
                    ),
                    "likely_same_position_next_vorp": rounded(
                        same_position_vorp
                    ),
                    "value_lost_if_waiting": rounded(wait_cost),
                    "expert_rank_sd": row["expert_rank_sd"],
                    "injury_status": row["injury_status"],
                    "opponent_signal_before_next_pick": (
                        "shadow only; excluded from v1 recommendation order"
                    ),
                    "why_in_pool": (
                        f"ESPN-projected {rounded(vorp)} points above "
                        f"{row['position']}{row['replacement_rank']} replacement; "
                        f"estimated {rounded(100 * at_pick['availability'])}% "
                        f"chance to be available at pick {decision_pick}."
                    ),
                    "consensus_as_of": row["consensus_as_of"],
                    "calibration_seasons": (
                        "2024,2025 exploratory; 2026 prospective"
                    ),
                    "availability_method": (
                        "Beta(1,1)-smoothed global/position draft-residual blend; "
                        "position weight n/(n+20)"
                    ),
                    "rankings_source_url": manifest.get("sources", {}).get(
                        "dynastyprocess_rankings", ""
                    ),
                    "espn_source_url": manifest.get("sources", {}).get("espn", ""),
                }
            )
    return decisions


def build_board_rows(
    context: LeagueContext,
    snapshot_dir: Path,
    id_path: Path,
    draft_payload: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = read_json(snapshot_dir / "manifest.json")
    espn_payload = read_json(snapshot_dir / "espn-players.json")
    rankings = read_csv_rows(snapshot_dir / "dynastyprocess-rankings.csv")
    id_rows = read_csv_rows(id_path)
    if draft_payload is None:
        draft_payload = read_json(snapshot_dir / "espn-draft.json")

    espn_entries = {
        int(entry["id"]): entry
        for entry in espn_payload.get("players", [])
        if entry.get("player", {}).get("active", True)
        and ESPN_POSITION_IDS.get(entry.get("player", {}).get("defaultPositionId"))
        in context.allowed_positions
    }
    espn_by_name_position: dict[tuple[str, str], int] = {}
    for espn_id, entry in espn_entries.items():
        player = entry["player"]
        position = ESPN_POSITION_IDS[player["defaultPositionId"]]
        espn_by_name_position[(canonical_name(player["fullName"]), position)] = espn_id

    fp_to_espn = {
        fp_id: espn_id
        for row in id_rows
        if (fp_id := integer(row.get("fantasypros_id"))) is not None
        and (espn_id := integer(row.get("espn_id"))) is not None
    }
    consensus_rows = [
        row
        for row in rankings
        if row.get("page_type") == "redraft-overall"
        and row.get("fp_page") == "/nfl/rankings/ppr-cheatsheets.php"
        and row.get("pos") in context.allowed_positions
    ]
    consensus_rows.sort(key=lambda row: number(row.get("ecr")) or float("inf"))

    position_counts: dict[str, int] = {}
    consensus_by_espn: dict[int, dict[str, Any]] = {}
    match_methods: dict[int, str] = {}
    unmatched_consensus: list[dict[str, str]] = []
    for consensus_rank, consensus in enumerate(consensus_rows, start=1):
        position = consensus["pos"]
        consensus["consensus_rank"] = consensus_rank
        position_counts[position] = position_counts.get(position, 0) + 1
        consensus["position_rank"] = position_counts[position]
        fp_id = integer(consensus.get("id"))
        espn_id = fp_to_espn.get(fp_id) if fp_id is not None else None
        match_method = "id"
        if espn_id not in espn_entries:
            espn_id = espn_by_name_position.get(
                (canonical_name(consensus.get("player", "")), position)
            )
            match_method = "exact_name_position"
        if espn_id is None or espn_id not in espn_entries:
            unmatched_consensus.append(consensus)
            continue
        existing = consensus_by_espn.get(espn_id)
        if existing is None or (number(consensus["ecr"]) or 9999) < (
            number(existing["ecr"]) or 9999
        ):
            consensus_by_espn[espn_id] = consensus
            match_methods[espn_id] = match_method

    drafted = {
        int(pick["playerId"]): pick
        for pick in draft_picks(draft_payload)
        if pick.get("playerId") is not None
    }
    rows: list[dict[str, Any]] = []
    for espn_id, entry in espn_entries.items():
        player = entry["player"]
        position = ESPN_POSITION_IDS[player["defaultPositionId"]]
        consensus = consensus_by_espn.get(espn_id, {})
        ownership = player.get("ownership", {}) or {}
        rank = player.get("draftRanksByRankType", {}).get("PPR", {}) or {}
        ecr = number(consensus.get("consensus_rank"))
        expert_average_rank = number(consensus.get("ecr"))
        espn_adp = number(ownership.get("averageDraftPosition"))
        espn_rank = number(rank.get("rank"))
        best = number(consensus.get("best"))
        worst = number(consensus.get("worst"))
        drafted_pick = drafted.get(espn_id, {})
        rows.append(
            {
                "available": "no" if drafted_pick else "yes",
                "consensus_rank": rounded(ecr),
                "player": player.get("fullName"),
                "team": consensus.get("team") or consensus.get("tm") or "",
                "position": position,
                "position_rank": consensus.get("position_rank", ""),
                "expert_average_rank": rounded(expert_average_rank),
                "espn_adp": rounded(espn_adp),
                "adp_minus_ecr": rounded(
                    espn_adp - ecr if espn_adp is not None and ecr is not None else None
                ),
                "espn_ppr_rank": rounded(espn_rank),
                "espn_rank_minus_ecr": rounded(
                    espn_rank - ecr
                    if espn_rank is not None and ecr is not None
                    else None
                ),
                "espn_projected_points": rounded(
                    season_projection(player, context.season)
                ),
                "expert_best_rank": rounded(best),
                "expert_worst_rank": rounded(worst),
                "expert_rank_sd": rounded(number(consensus.get("sd"))),
                "expert_rank_range": rounded(
                    worst - best if worst is not None and best is not None else None
                ),
                "espn_average_auction_value": rounded(
                    number(ownership.get("auctionValueAverage"))
                ),
                "espn_rank_auction_value": rounded(number(rank.get("auctionValue"))),
                "injury_status": player.get("injuryStatus") or "",
                "injured": "yes" if player.get("injured") else "no",
                "last_news_at": timestamp_millis(player.get("lastNewsDate")),
                "percent_owned": rounded(number(ownership.get("percentOwned"))),
                "bye_week": consensus.get("bye") or "",
                "espn_id": espn_id,
                "fantasypros_id": consensus.get("id") or "",
                "match_method": match_methods.get(espn_id, "unmatched"),
                "drafted_overall": drafted_pick.get("overallPickNumber", ""),
                "drafted_by_team_id": drafted_pick.get("teamId", ""),
                "consensus_as_of": manifest.get("dynastyprocess_consensus_as_of", ""),
                "snapshot_at": manifest.get("captured_at", ""),
            }
        )

    replacement_levels = starter_replacement_levels(context, rows)
    for row in rows:
        level = replacement_levels.get(row["position"])
        projection = number(row.get("espn_projected_points"))
        if level is None or projection is None:
            row["replacement_rank"] = ""
            row["replacement_points"] = ""
            row["value_over_replacement"] = ""
            continue
        replacement_points = float(level["points"])
        row["replacement_rank"] = level["rank"]
        row["replacement_points"] = rounded(replacement_points)
        row["value_over_replacement"] = rounded(projection - replacement_points)

    rows.sort(
        key=lambda row: (
            row["available"] != "yes",
            number(row["consensus_rank"]) or float("inf"),
            number(row["espn_ppr_rank"]) or float("inf"),
            number(row["espn_adp"]) or float("inf"),
        )
    )
    top_consensus = consensus_rows[:200]
    top_matched = sum(
        1
        for consensus in top_consensus
        if (fp_to_espn.get(integer(consensus.get("id"))) in espn_entries)
        or (
            espn_by_name_position.get(
                (canonical_name(consensus.get("player", "")), consensus.get("pos", ""))
            )
            in espn_entries
        )
    )
    if top_matched < 190:
        raise RuntimeError(
            f"Only {top_matched}/200 top consensus players matched ESPN; "
            "refresh the reference crosswalk."
        )

    pick_numbers = [integer(pick.get("overallPickNumber")) for pick in drafted.values()]
    current_pick = max((pick for pick in pick_numbers if pick is not None), default=0)
    upcoming_user_picks = [
        pick for pick in user_pick_sequence(context) if pick > current_pick
    ]
    summary = {
        "snapshot": snapshot_dir.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "board_players": len(rows),
        "consensus_players": len(consensus_rows),
        "consensus_matches": len(consensus_by_espn),
        "top_200_consensus_matches": top_matched,
        "unmatched_consensus_players": len(unmatched_consensus),
        "drafted_players": len(drafted),
        "last_overall_pick": current_pick,
        "next_user_pick": upcoming_user_picks[0] if upcoming_user_picks else None,
        "upcoming_user_picks": upcoming_user_picks,
        "positive_adp_minus_ecr_means": (
            "Consensus ranks the player earlier than the ESPN market drafts him."
        ),
    }
    return rows, summary


def print_top_available(rows: list[dict[str, Any]], limit: int = 15) -> None:
    print("\nTop available by FantasyPros consensus:", flush=True)
    print(" ECR  Player                     Pos  ESPN ADP  ADP-ECR  Injury", flush=True)
    for row in (row for row in rows if row["available"] == "yes"):
        print(
            f"{str(row['consensus_rank']):>5}  "
            f"{str(row['player'])[:26]:<26} "
            f"{row['position']:<4} "
            f"{str(row['espn_adp']):>8} "
            f"{str(row['adp_minus_ecr']):>8}  "
            f"{row['injury_status']}",
            flush=True,
        )
        limit -= 1
        if limit == 0:
            break


def archive_live_decision(
    data_dir: Path,
    snapshot_dir: Path,
    draft_payload: dict[str, Any],
    live_rows: list[dict[str, Any]],
    recommendation: dict[str, Any],
) -> Path | None:
    """Write one immutable decision package when the configured team is on the clock."""
    if not recommendation["on_clock"] or recommendation["next_user_pick"] is None:
        return None
    observed_picks = [
        {
            "overall_pick": integer(pick.get("overallPickNumber")),
            "player_id": integer(pick.get("playerId")),
            "team_id": integer(pick.get("teamId")),
        }
        for pick in draft_picks(draft_payload)
    ]
    state_bytes = json.dumps(
        observed_picks, separators=(",", ":"), sort_keys=True
    ).encode()
    state_sha256 = hashlib.sha256(state_bytes).hexdigest()
    pick_number = int(recommendation["next_user_pick"])
    package_dir = (
        data_dir
        / "decisions"
        / snapshot_dir.name
        / f"pick-{pick_number:03d}"
        / f"after-{recommendation['last_overall_pick']:03d}-{state_sha256[:12]}"
    )
    script_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest_sha256 = hashlib.sha256(
        (snapshot_dir / "manifest.json").read_bytes()
    ).hexdigest()
    if package_dir.exists():
        existing = read_json(package_dir / "decision-state.json")
        if existing.get("observed_state_sha256") != state_sha256:
            raise RuntimeError(f"Decision archive collision at {package_dir}.")
        if (
            existing.get("draft_board_code_sha256") != script_sha256
            or existing.get("source_manifest_sha256") != manifest_sha256
        ):
            raise RuntimeError(
                "This draft state was already archived under different frozen "
                "code or source data. Preserve the original decision package."
            )
        return package_dir
    package_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        package_dir / "decision-state.json",
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "pick_number": pick_number,
            "observed_through_pick": recommendation["last_overall_pick"],
            "observed_picks": observed_picks,
            "observed_state_sha256": state_sha256,
            "source_snapshot": snapshot_dir.name,
            "source_manifest_sha256": manifest_sha256,
            "draft_board_code_sha256": script_sha256,
        },
    )
    write_json(package_dir / "recommendation.json", recommendation)
    write_csv(
        package_dir / "available-candidates.csv",
        live_rows,
        fieldnames=LIVE_RANKING_FIELDS,
    )
    print(f"[decision archived] {package_dir}", flush=True)
    return package_dir


def build(
    context: LeagueContext,
    data_dir: Path,
    snapshot_dir: Path,
    draft_payload: dict[str, Any] | None = None,
    archive_on_clock: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    id_path = reference_path(data_dir)
    if not id_path.exists():
        raise RuntimeError("Player-ID reference missing. Run refresh first.")
    if draft_payload is None:
        draft_payload = read_json(snapshot_dir / "espn-draft.json")
    rows, summary = build_board_rows(
        context, snapshot_dir, id_path, draft_payload=draft_payload
    )
    comparison_snapshot = previous_snapshot(data_dir, snapshot_dir)
    if comparison_snapshot is not None:
        comparison_rows, _ = build_board_rows(
            context, comparison_snapshot, id_path
        )
        source_changes = build_source_changes(
            comparison_rows,
            rows,
            comparison_snapshot.name,
            snapshot_dir.name,
        )
    else:
        source_changes = []
    database_path = data_dir.parent / "optasy.sqlite"
    calibration_samples = load_calibration_samples(
        context, data_dir, database_path
    )
    manifest = read_json(snapshot_dir / "manifest.json")
    decision_rows = build_opening_decision_rows(
        context, rows, calibration_samples, manifest
    )
    live_rows, recommendation = build_live_rankings(
        context, rows, calibration_samples, draft_payload
    )
    recommendation.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_snapshot": snapshot_dir.name,
            "source_snapshot_at": manifest.get("captured_at"),
        }
    )
    summary.update(
        {
            "decision_objective": (
                "Projected season starter points above league-specific replacement"
            ),
            "decision_ordering": (
                "Primary order uses value_over_replacement; availability and "
                "wait-cost fields are disclosed secondary evidence, not an "
                "opaque weighted score."
            ),
            "calibration_samples": len(calibration_samples),
            "calibration_status": (
                "2024-2025 exploratory because both seasons informed design; "
                "2026 is prospective"
            ),
            "opening_decision_picks": user_pick_sequence(context)[
                :OPENING_DECISION_COUNT
            ],
            "user_team_id": recommendation["user_team_id"],
            "last_overall_pick": recommendation["last_overall_pick"],
            "next_user_pick": recommendation["next_user_pick"],
            "upcoming_user_picks": recommendation["upcoming_user_picks"],
            "picks_until_user_turn": recommendation["picks_until_user_turn"],
            "on_clock": recommendation["on_clock"],
            "current_recommendation": recommendation["recommendation"],
            "source_change_comparison_snapshot": (
                comparison_snapshot.name if comparison_snapshot else None
            ),
            "source_change_records": len(source_changes),
        }
    )
    current_dir = data_dir / "current"
    write_csv(current_dir / "draft-board.csv", rows)
    write_csv(
        current_dir / "opening-decisions.csv",
        decision_rows,
        fieldnames=OPENING_DECISION_FIELDS,
    )
    write_csv(
        current_dir / "live-rankings.csv",
        live_rows,
        fieldnames=LIVE_RANKING_FIELDS,
    )
    write_json(current_dir / "current-recommendation.json", recommendation)
    write_csv(
        current_dir / "source-changes.csv",
        source_changes,
        fieldnames=SOURCE_CHANGE_FIELDS,
    )
    priority_counts: dict[str, int] = {}
    for change in source_changes:
        priority = change["review_priority"]
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
    write_json(
        current_dir / "source-changes-summary.json",
        {
            "generated_at": recommendation["generated_at"],
            "previous_snapshot": (
                comparison_snapshot.name if comparison_snapshot else None
            ),
            "current_snapshot": snapshot_dir.name,
            "change_records": len(source_changes),
            "priority_counts": priority_counts,
            "monitoring_thresholds": {
                "projected_points_absolute_change": 10,
                "value_over_replacement_absolute_change": 10,
                "consensus_rank_absolute_change": 5,
                "espn_ppr_rank_absolute_change": 5,
                "injury_or_news_timestamp_change": "always_review",
            },
            "interpretation": (
                "Operational review priorities only; they do not enter the "
                "player-value score. Refreshed source projections and ranks "
                "flow into the rebuilt board directly."
            ),
        },
    )
    write_json(current_dir / "summary.json", summary)
    if archive_on_clock:
        archive_live_decision(
            data_dir,
            snapshot_dir,
            draft_payload,
            live_rows,
            recommendation,
        )
    print(
        f"[build] players={summary['board_players']}, "
        f"consensus matches={summary['consensus_matches']}, "
        f"top-200 coverage={summary['top_200_consensus_matches']}/200, "
        f"drafted={summary['drafted_players']}, "
        f"next user pick={summary['next_user_pick']}",
        flush=True,
    )
    print(f"[board] {current_dir / 'draft-board.csv'}", flush=True)
    print(
        f"[opening decisions] rows={len(decision_rows)} "
        f"{current_dir / 'opening-decisions.csv'}",
        flush=True,
    )
    preferred = recommendation["recommendation"]
    print(
        f"[live recommendation] status={recommendation['status']} "
        f"pick={recommendation['next_user_pick']} "
        f"player={preferred['player'] if preferred else 'none'} "
        f"{current_dir / 'current-recommendation.json'}",
        flush=True,
    )
    print(
        f"[source changes] rows={len(source_changes)} "
        f"{current_dir / 'source-changes.csv'}",
        flush=True,
    )
    print_top_available(rows)
    return rows, summary


def watch(
    context: LeagueContext,
    credentials: EspnCredentials,
    data_dir: Path,
    snapshot_dir: Path,
    interval: float,
    once: bool,
) -> None:
    if interval < 2:
        raise RuntimeError("Watch interval must be at least two seconds.")
    previous_state_sha256: str | None = None
    previous_drafted: set[int] = set()
    print(f"[watch] polling ESPN every {interval:g} seconds", flush=True)
    while True:
        payload = fetch_espn_draft(context, credentials)
        picks = draft_picks(payload)
        drafted_ids = {
            int(pick["playerId"]) for pick in picks if pick.get("playerId") is not None
        }
        state_sha256 = draft_state_sha256(payload)
        if state_sha256 != previous_state_sha256:
            if previous_state_sha256 is not None:
                additions = drafted_ids - previous_drafted
                print(
                    f"[draft update] new players={len(additions)}; "
                    "selection or slot ownership changed",
                    flush=True,
                )
            write_json(data_dir / "current" / "live-draft.json", payload)
            build(
                context,
                data_dir,
                snapshot_dir,
                draft_payload=payload,
                archive_on_clock=True,
            )
            previous_drafted = drafted_ids
            previous_state_sha256 = state_sha256
        if once:
            return
        detail = payload.get("draftDetail", {})
        if detail.get("drafted") and not detail.get("inProgress"):
            print("[watch complete] ESPN reports that the draft is complete.", flush=True)
            return
        time.sleep(interval)


def main() -> int:
    args = parse_args()
    context = load_context(args.config)
    if args.command == "refresh":
        credentials = load_credentials(context)
        snapshot_dir = refresh(
            context, credentials, args.data_dir, args.refresh_reference
        )
        build(context, args.data_dir, snapshot_dir)
    elif args.command == "build":
        snapshot_dir = resolve_snapshot(args.data_dir, args.snapshot)
        build(context, args.data_dir, snapshot_dir)
    elif args.command == "freeze-sources":
        snapshot_dir = resolve_snapshot(args.data_dir, args.snapshot)
        build(context, args.data_dir, snapshot_dir)
        destination = freeze_draft_sources(
            context,
            args.data_dir,
            snapshot_dir,
            args.config,
            args.amendment_reason,
        )
        print(
            f"[sources frozen] snapshot={snapshot_dir.name} {destination}",
            flush=True,
        )
    else:
        credentials = load_credentials(context)
        snapshot_dir = (
            resolve_snapshot(args.data_dir, args.snapshot)
            if args.snapshot
            else resolve_frozen_draft_sources(
                context, args.data_dir, args.config
            )
        )
        watch(
            context,
            credentials,
            args.data_dir,
            snapshot_dir,
            args.interval,
            args.once,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
