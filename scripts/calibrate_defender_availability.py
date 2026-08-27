#!/usr/bin/env python3
"""Calibrate defender availability from historical injury reports and snap counts."""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import random
import shutil
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

import requests

if __package__:
    from .injury_snapshot import (
        NFLVERSE_RELEASE_ROOT,
        defensive_role,
        make_session,
        sha256_bytes,
    )
else:
    from injury_snapshot import (
        NFLVERSE_RELEASE_ROOT,
        defensive_role,
        make_session,
        sha256_bytes,
    )


DEFAULT_SEASONS = (2021, 2022, 2023, 2024)
TEST_SEASON = 2024
CELL_SHRINKAGE = 20
BOOTSTRAP_SAMPLES = 5_000
SCHEDULE_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
PLAYERS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
)
RECORD_FIELDS = [
    "season",
    "week",
    "team",
    "gsis_id",
    "pfr_id",
    "player_name",
    "raw_position",
    "role",
    "report_status",
    "practice_status",
    "primary_injury",
    "date_modified",
    "scheduled_kickoff_utc",
    "information_available_pre_kickoff",
    "played_defensive_snap",
    "defense_snap_share",
    "healthy_defense_snap_share_4g",
    "healthy_baseline_games",
    "defense_snap_retention",
    "split",
]
CALIBRATION_FIELDS = [
    "report_status",
    "practice_status",
    "train_n",
    "train_play_rate",
    "predicted_play_probability_report_only",
    "predicted_play_probability",
    "train_retention_n",
    "predicted_defense_snap_retention_report_only",
    "predicted_defense_snap_retention",
    "test_n",
    "test_play_rate",
    "test_retention_n",
    "test_defense_snap_retention",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", nargs="?", choices=("refresh", "build"), default="refresh"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/injury/calibration"))
    parser.add_argument("--seasons", nargs="+", type=int, default=list(DEFAULT_SEASONS))
    parser.add_argument(
        "--source-snapshot",
        type=Path,
        help="Historical source snapshot directory; defaults to the latest.",
    )
    return parser.parse_args()


def number(value: Any) -> float | None:
    if value in (None, "", "NA", "null"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def capture_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def stable_url(kind: str, season: int) -> str:
    if kind == "rosters":
        extension = "csv.gz" if season >= 2024 else "csv"
        return f"{NFLVERSE_RELEASE_ROOT}/rosters/roster_{season}.{extension}"
    if kind == "injuries":
        extension = "csv.gz" if season >= 2023 else "csv"
        return f"{NFLVERSE_RELEASE_ROOT}/injuries/injuries_{season}.{extension}"
    if kind == "snap_counts":
        return f"{NFLVERSE_RELEASE_ROOT}/snap_counts/snap_counts_{season}.csv.gz"
    raise ValueError(f"Unknown historical source kind: {kind}")


def download(url: str) -> bytes:
    with make_session() as session:
        response = session.get(url, timeout=90)
    response.raise_for_status()
    if len(response.content) < 10_000:
        raise RuntimeError(f"Unexpectedly small historical source: {url}")
    return response.content


def source_requests(seasons: list[int]) -> list[tuple[str, int, str]]:
    requests_to_make = [
        ("schedules", 0, SCHEDULE_URL),
        ("players", 0, PLAYERS_URL),
    ]
    for season in seasons:
        requests_to_make.append(("rosters", season, stable_url("rosters", season)))
        requests_to_make.append(("injuries", season, stable_url("injuries", season)))
    for season in range(min(seasons) - 1, max(seasons) + 1):
        requests_to_make.append(
            ("snap_counts", season, stable_url("snap_counts", season))
        )
    return requests_to_make


def refresh_sources(data_dir: Path, seasons: list[int]) -> Path:
    source_id = capture_id()
    parent = data_dir / "sources"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / source_id
    if destination.exists():
        raise FileExistsError(f"Historical source snapshot already exists: {destination}")
    staging = Path(tempfile.mkdtemp(prefix=f".{source_id}-", dir=parent))
    try:
        requests_to_make = source_requests(seasons)
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                (kind, season, url): executor.submit(download, url)
                for kind, season, url in requests_to_make
            }
            results = [
                (kind, season, url, futures[(kind, season, url)].result())
                for kind, season, url in requests_to_make
            ]
        files = []
        for kind, season, url, content in results:
            extension = ".csv.gz" if url.endswith(".gz") else ".csv"
            path = staging / f"{kind}-{season}{extension}"
            with path.open("xb") as output:
                output.write(content)
            files.append(
                {
                    "kind": kind,
                    "season": season,
                    "url": url,
                    "path": path.name,
                    "bytes": len(content),
                    "sha256": sha256_bytes(content),
                }
            )
        manifest = {
            "source_snapshot": source_id,
            "captured_at": iso_now(),
            "calibration_seasons": sorted(seasons),
            "test_season": TEST_SEASON,
            "files": files,
        }
        with (staging / "manifest.json").open("x", encoding="utf-8") as output:
            json.dump(manifest, output, indent=2, sort_keys=True)
            output.write("\n")
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


def latest_source_snapshot(data_dir: Path) -> Path:
    paths = sorted((data_dir / "sources").glob("*/manifest.json"))
    if not paths:
        raise RuntimeError("No historical source snapshot found. Run refresh first.")
    return paths[-1].parent


def read_source(path: Path) -> list[dict[str, str]]:
    content = path.read_bytes()
    if path.suffix == ".gz":
        content = gzip.decompress(content)
    return list(csv.DictReader(io.StringIO(content.decode("utf-8"))))


def source_file(
    source_dir: Path, manifest: dict[str, Any], kind: str, season: int
) -> Path:
    matches = [
        item
        for item in manifest["files"]
        if item["kind"] == kind and int(item["season"]) == season
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {kind} file for {season}; found {len(matches)}.")
    path = source_dir / matches[0]["path"]
    if sha256_bytes(path.read_bytes()) != matches[0]["sha256"]:
        raise RuntimeError(f"Historical source hash mismatch: {path}")
    return path


def report_category(value: str) -> str:
    normalized = "_".join(value.upper().replace("/", " ").replace("-", " ").split())
    return normalized or "NO_GAME_DESIGNATION"


def practice_category(value: str) -> str:
    normalized = value.upper()
    if "DID NOT PARTICIPATE" in normalized:
        return "DNP"
    if "LIMITED" in normalized:
        return "LIMITED"
    if "FULL" in normalized:
        return "FULL"
    return "NO_PRACTICE_DESIGNATION"


def roster_crosswalk(
    roster_by_season: dict[int, list[dict[str, str]]],
    player_rows: list[dict[str, str]] | None = None,
) -> tuple[
    dict[tuple[int, str, str], str],
    dict[tuple[int, str], str],
    dict[str, str],
]:
    exact: dict[tuple[int, str, str], str] = {}
    candidates: dict[tuple[int, str], set[str]] = defaultdict(set)
    for season, rows in roster_by_season.items():
        for row in rows:
            gsis_id = row.get("gsis_id") or ""
            pfr_id = row.get("pfr_id") or ""
            team = (row.get("team") or "").upper()
            if not gsis_id or not pfr_id:
                continue
            exact[(season, team, gsis_id)] = pfr_id
            candidates[(season, gsis_id)].add(pfr_id)
    unique = {
        key: next(iter(values)) for key, values in candidates.items() if len(values) == 1
    }
    global_ids = {
        row["gsis_id"]: row["pfr_id"]
        for row in (player_rows or [])
        if row.get("gsis_id") and row.get("pfr_id")
    }
    return exact, unique, global_ids


def snap_indexes(
    snap_by_season: dict[int, list[dict[str, str]]]
) -> tuple[
    dict[tuple[int, int, str, str], dict[str, str]],
    dict[str, list[tuple[int, int, float]]],
]:
    games: dict[tuple[int, int, str, str], dict[str, str]] = {}
    history: dict[str, list[tuple[int, int, float]]] = defaultdict(list)
    for season, rows in snap_by_season.items():
        for row in rows:
            if (row.get("game_type") or "") != "REG":
                continue
            week = int(number(row.get("week")) or 0)
            team = (row.get("team") or "").upper()
            pfr_id = row.get("pfr_player_id") or ""
            if not week or not team or not pfr_id:
                continue
            games[(season, week, team, pfr_id)] = row
            defense_pct = number(row.get("defense_pct"))
            defense_snaps = number(row.get("defense_snaps")) or 0
            if defense_pct is not None and defense_snaps > 0:
                history[pfr_id].append((season, week, defense_pct))
    for values in history.values():
        values.sort()
    return games, history


def kickoff_index(schedule_rows: list[dict[str, str]]) -> dict[tuple[int, int, str], datetime]:
    kickoffs: dict[tuple[int, int, str], datetime] = {}
    eastern = ZoneInfo("America/New_York")
    for row in schedule_rows:
        if (row.get("game_type") or "") != "REG":
            continue
        season = int(number(row.get("season")) or 0)
        week = int(number(row.get("week")) or 0)
        gameday = row.get("gameday") or ""
        gametime = row.get("gametime") or ""
        away_team = (row.get("away_team") or "").upper()
        home_team = (row.get("home_team") or "").upper()
        if not season or not week or not gameday or not gametime:
            continue
        local_kickoff = datetime.fromisoformat(f"{gameday}T{gametime}").replace(
            tzinfo=eastern
        )
        kickoff = local_kickoff.astimezone(timezone.utc)
        for team in (away_team, home_team):
            if team:
                kickoffs[(season, week, team)] = kickoff
    return kickoffs


def prior_baseline(
    history: list[tuple[int, int, float]], season: int, week: int
) -> tuple[float | None, int]:
    prior = [value for prior_season, prior_week, value in history if (prior_season, prior_week) < (season, week)][-4:]
    return (sum(prior) / len(prior), len(prior)) if prior else (None, 0)


def build_records(
    seasons: list[int],
    injury_by_season: dict[int, list[dict[str, str]]],
    roster_by_season: dict[int, list[dict[str, str]]],
    snap_by_season: dict[int, list[dict[str, str]]],
    schedule_rows: list[dict[str, str]],
    timing_audit: dict[str, int] | None = None,
    player_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    timing_audit = timing_audit if timing_audit is not None else {}
    timing_audit.setdefault("pre_kickoff_source_rows", 0)
    timing_audit.setdefault("post_kickoff_source_rows_excluded", 0)
    timing_audit.setdefault("missing_schedule_source_rows_excluded", 0)
    timing_audit.setdefault("pre_kickoff_unique_player_weeks", 0)
    timing_audit.setdefault("unmatched_player_id_player_weeks_excluded", 0)
    exact_ids, unique_ids, global_ids = roster_crosswalk(
        roster_by_season, player_rows
    )
    snap_games, snap_history = snap_indexes(snap_by_season)
    kickoffs = kickoff_index(schedule_rows)
    records: list[dict[str, Any]] = []
    for season in seasons:
        latest_reports: dict[tuple[str, int, str], dict[str, str]] = {}
        for injury in injury_by_season[season]:
            if (injury.get("game_type") or "") != "REG":
                continue
            week = int(number(injury.get("week")) or 0)
            team = (injury.get("team") or "").upper()
            gsis_id = injury.get("gsis_id") or ""
            role = defensive_role(injury.get("position") or "")
            if not week or not team or not gsis_id or role is None:
                continue
            kickoff = kickoffs.get((season, week, team))
            modified_at_raw = injury.get("date_modified") or ""
            if kickoff is None:
                timing_audit["missing_schedule_source_rows_excluded"] += 1
                continue
            if not modified_at_raw:
                raise RuntimeError(
                    f"Missing injury timestamp for {season} week {week} {team} {gsis_id}."
                )
            modified_at = datetime.fromisoformat(
                modified_at_raw.replace("Z", "+00:00")
            )
            if modified_at.tzinfo is None:
                modified_at = modified_at.replace(tzinfo=timezone.utc)
            if modified_at >= kickoff:
                timing_audit["post_kickoff_source_rows_excluded"] += 1
                continue
            timing_audit["pre_kickoff_source_rows"] += 1
            key = (team, week, gsis_id)
            existing = latest_reports.get(key)
            if existing is None or (injury.get("date_modified") or "") > (
                existing.get("date_modified") or ""
            ):
                latest_reports[key] = injury

        for (team, week, gsis_id), injury in latest_reports.items():
            timing_audit["pre_kickoff_unique_player_weeks"] += 1
            kickoff = kickoffs.get((season, week, team))
            if kickoff is None:  # Guarded while filtering source rows above.
                raise AssertionError("Kickoff disappeared from the schedule index.")
            pfr_id = (
                exact_ids.get((season, team, gsis_id))
                or unique_ids.get((season, gsis_id))
                or global_ids.get(gsis_id)
            )
            if not pfr_id:
                timing_audit["unmatched_player_id_player_weeks_excluded"] += 1
                continue
            snap = snap_games.get((season, week, team, pfr_id))
            defense_snaps = number(snap.get("defense_snaps")) if snap else 0
            played_defense = int((defense_snaps or 0) > 0)
            defense_pct = number(snap.get("defense_pct")) if snap else 0.0
            baseline, baseline_games = prior_baseline(
                snap_history.get(pfr_id, []), season, week
            )
            retention = (
                min(max((defense_pct or 0) / baseline, 0), 1)
                if baseline is not None and baseline > 0 and baseline_games >= 2
                else None
            )
            records.append(
                {
                    "season": season,
                    "week": week,
                    "team": team,
                    "gsis_id": gsis_id,
                    "pfr_id": pfr_id,
                    "player_name": injury.get("full_name") or "",
                    "raw_position": injury.get("position") or "",
                    "role": defensive_role(injury.get("position") or "") or "",
                    "report_status": report_category(injury.get("report_status") or ""),
                    "practice_status": practice_category(
                        injury.get("practice_status") or ""
                    ),
                    "primary_injury": (
                        injury.get("report_primary_injury")
                        or injury.get("practice_primary_injury")
                        or ""
                    ),
                    "date_modified": injury.get("date_modified") or "",
                    "scheduled_kickoff_utc": kickoff.isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "information_available_pre_kickoff": 1,
                    "played_defensive_snap": played_defense,
                    "defense_snap_share": round(defense_pct or 0, 6),
                    "healthy_defense_snap_share_4g": (
                        "" if baseline is None else round(baseline, 6)
                    ),
                    "healthy_baseline_games": baseline_games,
                    "defense_snap_retention": (
                        "" if retention is None else round(retention, 6)
                    ),
                    "split": "test" if season == TEST_SEASON else "train",
                }
            )
    records.sort(key=lambda row: (row["season"], row["week"], row["team"], row["player_name"]))
    timing_audit["unique_player_weeks_included"] = len(records)
    return records


def grouped_values(
    records: list[dict[str, Any]],
    key: Callable[[dict[str, Any]], tuple[str, ...]],
    value: Callable[[dict[str, Any]], float | None],
) -> dict[tuple[str, ...], list[float]]:
    groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for record in records:
        candidate = value(record)
        if candidate is not None:
            groups[key(record)].append(candidate)
    return groups


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def fit_predictors(
    train: list[dict[str, Any]],
) -> tuple[
    Callable[[dict[str, Any]], float],
    Callable[[dict[str, Any]], float],
    Callable[[dict[str, Any]], float],
    Callable[[dict[str, Any]], float],
]:
    play_value = lambda row: float(row["played_defensive_snap"])
    status_key = lambda row: (str(row["report_status"]),)
    cell_key = lambda row: (str(row["report_status"]), str(row["practice_status"]))
    global_play = (sum(play_value(row) for row in train) + 1) / (len(train) + 2)
    status_play = grouped_values(train, status_key, play_value)
    cell_play = grouped_values(train, cell_key, play_value)

    retention_value = lambda row: number(row.get("defense_snap_retention"))
    retention_rows = [row for row in train if retention_value(row) is not None]
    global_retention = mean([retention_value(row) or 0 for row in retention_rows])
    status_retention = grouped_values(train, status_key, retention_value)
    cell_retention = grouped_values(train, cell_key, retention_value)

    def status_probability(row: dict[str, Any]) -> float:
        values = status_play.get(status_key(row), [])
        return (
            (sum(values) + CELL_SHRINKAGE * global_play)
            / (len(values) + CELL_SHRINKAGE)
            if values
            else global_play
        )

    def play_probability(row: dict[str, Any]) -> float:
        parent = status_probability(row)
        values = cell_play.get(cell_key(row), [])
        return (
            (sum(values) + CELL_SHRINKAGE * parent)
            / (len(values) + CELL_SHRINKAGE)
            if values
            else parent
        )

    def status_retention_prediction(row: dict[str, Any]) -> float:
        status_values = status_retention.get(status_key(row), [])
        return (
            (sum(status_values) + CELL_SHRINKAGE * global_retention)
            / (len(status_values) + CELL_SHRINKAGE)
            if status_values
            else global_retention
        )

    def retention_prediction(row: dict[str, Any]) -> float:
        parent = status_retention_prediction(row)
        values = cell_retention.get(cell_key(row), [])
        prediction = (
            (sum(values) + CELL_SHRINKAGE * parent)
            / (len(values) + CELL_SHRINKAGE)
            if values
            else parent
        )
        return min(prediction, status_probability(row))

    return (
        status_probability,
        play_probability,
        status_retention_prediction,
        retention_prediction,
    )


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(probability * (len(ordered) - 1))))
    return ordered[index]


def bootstrap_mean_ci(
    values: list[float], block_ids: list[str]
) -> dict[str, float]:
    if len(values) != len(block_ids) or not values:
        raise ValueError("Bootstrap values and block IDs must be nonempty and aligned.")
    blocks: dict[str, list[float]] = defaultdict(list)
    for block_id, value in zip(block_ids, values):
        blocks[block_id].append(value)
    block_values = list(blocks.values())
    generator = random.Random(20260825)
    estimates = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled = [
            block_values[generator.randrange(len(block_values))]
            for _ in block_values
        ]
        estimates.append(sum(map(sum, sampled)) / sum(map(len, sampled)))
    return {
        "mean": round(mean(values), 8),
        "lower_95": round(percentile(estimates, 0.025), 8),
        "upper_95": round(percentile(estimates, 0.975), 8),
    }


def evaluate(
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    train = [row for row in records if row["split"] == "train"]
    test = [row for row in records if row["split"] == "test"]
    if len(train) < 1_000 or len(test) < 300:
        raise RuntimeError(
            f"Insufficient calibration records: train={len(train)} test={len(test)}"
        )
    (
        status_predict,
        model_predict,
        status_retention_predict,
        retention_predict,
    ) = fit_predictors(train)
    global_play = (
        sum(float(row["played_defensive_snap"]) for row in train) + 1
    ) / (len(train) + 2)
    global_retention_values = [
        value
        for row in train
        if (value := number(row.get("defense_snap_retention"))) is not None
    ]
    global_retention = mean(global_retention_values)

    status_losses = []
    model_losses = []
    paired_improvements = []
    log_losses = []
    for row in test:
        outcome = float(row["played_defensive_snap"])
        status_probability = status_predict(row)
        model_probability = model_predict(row)
        status_loss = (outcome - status_probability) ** 2
        model_loss = (outcome - model_probability) ** 2
        status_losses.append(status_loss)
        model_losses.append(model_loss)
        paired_improvements.append(status_loss - model_loss)
        clipped = min(max(model_probability, 1e-9), 1 - 1e-9)
        log_losses.append(
            -(outcome * math.log(clipped) + (1 - outcome) * math.log(1 - clipped))
        )
    test_week_blocks = [f"{row['season']}-w{row['week']}" for row in test]

    retention_test = [
        row
        for row in test
        if number(row.get("defense_snap_retention")) is not None
    ]
    retention_model_errors = [
        abs((number(row["defense_snap_retention"]) or 0) - retention_predict(row))
        for row in retention_test
    ]
    retention_status_errors = [
        abs(
            (number(row["defense_snap_retention"]) or 0)
            - status_retention_predict(row)
        )
        for row in retention_test
    ]
    retention_global_errors = [
        abs((number(row["defense_snap_retention"]) or 0) - global_retention)
        for row in retention_test
    ]

    train_groups = grouped_values(
        train,
        lambda row: (str(row["report_status"]), str(row["practice_status"])),
        lambda row: float(row["played_defensive_snap"]),
    )
    test_groups = grouped_values(
        test,
        lambda row: (str(row["report_status"]), str(row["practice_status"])),
        lambda row: float(row["played_defensive_snap"]),
    )
    train_retention = grouped_values(
        train,
        lambda row: (str(row["report_status"]), str(row["practice_status"])),
        lambda row: number(row.get("defense_snap_retention")),
    )
    test_retention = grouped_values(
        test,
        lambda row: (str(row["report_status"]), str(row["practice_status"])),
        lambda row: number(row.get("defense_snap_retention")),
    )
    keys = sorted(set(train_groups) | set(test_groups))
    calibration = []
    for key in keys:
        template = {"report_status": key[0], "practice_status": key[1]}
        train_values = train_groups.get(key, [])
        test_values = test_groups.get(key, [])
        train_retention_values = train_retention.get(key, [])
        test_retention_values = test_retention.get(key, [])
        calibration.append(
            {
                **template,
                "train_n": len(train_values),
                "train_play_rate": round(mean(train_values), 6) if train_values else "",
                "predicted_play_probability_report_only": round(
                    status_predict(template), 6
                ),
                "predicted_play_probability": round(model_predict(template), 6),
                "train_retention_n": len(train_retention_values),
                "predicted_defense_snap_retention_report_only": round(
                    status_retention_predict(template), 6
                ),
                "predicted_defense_snap_retention": round(
                    retention_predict(template), 6
                ),
                "test_n": len(test_values),
                "test_play_rate": round(mean(test_values), 6) if test_values else "",
                "test_retention_n": len(test_retention_values),
                "test_defense_snap_retention": (
                    round(mean(test_retention_values), 6)
                    if test_retention_values
                    else ""
                ),
            }
        )

    evaluation = {
        "method_status": "exploratory_historical_calibration",
        "train_seasons": sorted({int(row["season"]) for row in train}),
        "test_season": TEST_SEASON,
        "train_records": len(train),
        "test_records": len(test),
        "test_defensive_participation_rate": round(
            mean([float(row["played_defensive_snap"]) for row in test]), 8
        ),
        "play_probability": {
            "global_baseline_brier": round(
                mean(
                    [
                        (float(row["played_defensive_snap"]) - global_play) ** 2
                        for row in test
                    ]
                ),
                8,
            ),
            "report_status_brier": round(mean(status_losses), 8),
            "report_plus_practice_brier": round(mean(model_losses), 8),
            "report_plus_practice_log_loss": round(mean(log_losses), 8),
            "paired_brier_improvement_vs_global": bootstrap_mean_ci(
                [
                    (float(row["played_defensive_snap"]) - global_play) ** 2
                    - model_loss
                    for row, model_loss in zip(test, model_losses)
                ],
                test_week_blocks,
            ),
            "paired_brier_improvement_vs_report_status": bootstrap_mean_ci(
                paired_improvements, test_week_blocks
            ),
        },
        "defense_snap_retention": {
            "test_records_with_prior_baseline": len(retention_test),
            "global_mean_mae": round(mean(retention_global_errors), 8),
            "report_status_mae": round(mean(retention_status_errors), 8),
            "report_plus_practice_mae": round(mean(retention_model_errors), 8),
            "paired_mae_improvement_vs_global": bootstrap_mean_ci(
                [
                    global_error - model_error
                    for global_error, model_error in zip(
                        retention_global_errors, retention_model_errors
                    )
                ],
                [f"{row['season']}-w{row['week']}" for row in retention_test],
            ),
            "paired_mae_improvement_vs_report_status": bootstrap_mean_ci(
                [
                    status_error - model_error
                    for status_error, model_error in zip(
                        retention_status_errors, retention_model_errors
                    )
                ],
                [f"{row['season']}-w{row['week']}" for row in retention_test],
            ),
        },
        "uncertainty": {
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "bootstrap_resampling_unit": "season_week",
        },
        "limitations": [
            "2021-2023 informed the model and 2024 is the temporal test; none is prospective.",
            "Participation means at least one defensive snap, not merely being active.",
            "Defensive snap retention is capped at one relative to the prior four appearances.",
            "This calibrates availability, not the fantasy impact of a defender's absence.",
        ],
    }
    status_keys = sorted({str(row["report_status"]) for row in train})
    cell_keys = sorted(
        {
            (str(row["report_status"]), str(row["practice_status"]))
            for row in train
        }
    )
    model = {
        "schema_version": 1,
        "model_version": "defender-availability-v0",
        "method_status": "experimental_historical_prior",
        "train_seasons": sorted({int(row["season"]) for row in train}),
        "test_season": TEST_SEASON,
        "cell_shrinkage": CELL_SHRINKAGE,
        "binary_prediction_rule": "report_status_only",
        "retention_prediction_rule": "report_plus_practice",
        "global": {
            "defensive_participation_probability": round(global_play, 8),
            "expected_defense_snap_retention": round(global_retention, 8),
        },
        "report_status": {
            status: {
                "train_n": len(
                    [row for row in train if row["report_status"] == status]
                ),
                "defensive_participation_probability": round(
                    status_predict({"report_status": status}), 8
                ),
                "expected_defense_snap_retention": round(
                    status_retention_predict({"report_status": status}), 8
                ),
            }
            for status in status_keys
        },
        "report_plus_practice": {
            f"{status}|{practice}": {
                "train_n": len(
                    [
                        row
                        for row in train
                        if row["report_status"] == status
                        and row["practice_status"] == practice
                    ]
                ),
                "defensive_participation_probability": round(
                    model_predict(
                        {"report_status": status, "practice_status": practice}
                    ),
                    8,
                ),
                "expected_defense_snap_retention": round(
                    retention_predict(
                        {"report_status": status, "practice_status": practice}
                    ),
                    8,
                ),
            }
            for status, practice in cell_keys
        },
        "activation_constraints": [
            "Use only for defenders appearing on an injury/practice report.",
            "Use only at final_status or inactive information vintages.",
            "Override official Out and reserve-list statuses to zero.",
            "Do not interpret lost snap capacity as a fantasy-point adjustment.",
        ],
    }
    return evaluation, calibration, model


def atomic_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
    temporary.replace(path)


def build(data_dir: Path, source_dir: Path, seasons: list[int]) -> dict[str, Any]:
    manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    injury_by_season = {
        season: read_source(source_file(source_dir, manifest, "injuries", season))
        for season in seasons
    }
    roster_by_season = {
        season: read_source(source_file(source_dir, manifest, "rosters", season))
        for season in seasons
    }
    snap_by_season = {
        season: read_source(source_file(source_dir, manifest, "snap_counts", season))
        for season in range(min(seasons) - 1, max(seasons) + 1)
    }
    schedule_rows = read_source(source_file(source_dir, manifest, "schedules", 0))
    player_rows = read_source(source_file(source_dir, manifest, "players", 0))
    timing_audit: dict[str, int] = {}
    records = build_records(
        seasons,
        injury_by_season,
        roster_by_season,
        snap_by_season,
        schedule_rows,
        timing_audit,
        player_rows,
    )
    evaluation, calibration, model = evaluate(records)
    evaluation.update(
        {
            "generated_at": iso_now(),
            "source_snapshot": manifest["source_snapshot"],
            "record_count": len(records),
            "information_timing_audit": timing_audit,
        }
    )
    output_dir = data_dir / "current"
    atomic_csv(output_dir / "availability-records.csv", RECORD_FIELDS, records)
    atomic_csv(output_dir / "availability-calibration.csv", CALIBRATION_FIELDS, calibration)
    atomic_json(output_dir / "availability-evaluation.json", evaluation)
    model.update(
        {
            "source_snapshot": manifest["source_snapshot"],
            "generated_at": evaluation["generated_at"],
        }
    )
    atomic_json(output_dir / "availability-model.json", model)
    return evaluation


def main() -> int:
    args = parse_args()
    try:
        seasons = sorted(set(args.seasons))
        if TEST_SEASON not in seasons or max(seasons) != TEST_SEASON:
            raise ValueError(f"The temporal test season must remain {TEST_SEASON}.")
        source_dir = args.source_snapshot
        if args.command == "refresh":
            source_dir = refresh_sources(args.data_dir, seasons)
            print(f"[historical sources] {source_dir}")
        source_dir = source_dir or latest_source_snapshot(args.data_dir)
        evaluation = build(args.data_dir, source_dir, seasons)
    except (OSError, RuntimeError, ValueError, requests.RequestException) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    play = evaluation["play_probability"]
    retention = evaluation["defense_snap_retention"]
    print(
        f"[availability calibration] train={evaluation['train_records']} "
        f"test={evaluation['test_records']} "
        f"brier={play['report_plus_practice_brier']} "
        f"retention_mae={retention['report_plus_practice_mae']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
