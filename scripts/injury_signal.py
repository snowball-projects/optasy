#!/usr/bin/env python3
# Copyright 2026 snowball
# SPDX-License-Identifier: Apache-2.0
"""Build transparent defender-level availability features from one snapshot."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
import tempfile
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if __package__:
    from .injury_snapshot import manifest_paths, sha256_file, verify_snapshot
else:
    from injury_snapshot import manifest_paths, sha256_file, verify_snapshot


EXPOSURE_FIELDS = [
    "snapshot_id",
    "as_of",
    "source",
    "source_player_id",
    "player_name",
    "team",
    "reported_role",
    "game_status",
    "practice_status",
    "probability_playing",
    "probability_source",
    "availability_known",
    "availability_model_version",
    "context_match_method",
    "context_player_id",
    "normalized_role",
    "roster_status",
    "depth_position",
    "depth_rank",
    "healthy_snap_share_4g",
    "absence_probability",
    "absence_snap_capacity_lower_bound",
    "expected_defense_snap_retention",
    "retention_source",
    "expected_lost_snap_fraction",
    "expected_lost_snap_capacity",
    "replacement_player",
    "replacement_depth_rank",
    "replacement_roster_status",
    "replacement_prior_snap_share_4g",
    "quality_gap_status",
]
UNIT_FIELDS = [
    "snapshot_id",
    "as_of",
    "team",
    "role",
    "injury_records",
    "matched_defenders",
    "known_availability",
    "unknown_availability",
    "projected_starters_affected",
    "absence_snap_capacity_lower_bound",
    "expected_lost_snap_capacity",
    "cluster_flag",
    "interpretation",
]
CERTAIN_OUT_STATUSES = {
    "OUT",
    "INJURY_RESERVE",
    "INJURED_RESERVE",
    "IR",
    "PUP",
    "PHYSICALLY_UNABLE_TO_PERFORM",
    "SUSPENDED",
    "SUSPENSION",
}
DEFAULT_AVAILABILITY_MODEL = (
    Path(__file__).resolve().parents[1] / "config" / "defender-availability-v0.json"
)
CALIBRATED_VINTAGES = {"final_status", "inactive"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/injury"))
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Snapshot directory; defaults to the latest valid snapshot.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Defaults to DATA_DIR/current.",
    )
    parser.add_argument(
        "--freeze",
        action="store_true",
        help="Write an immutable prediction artifact under DATA_DIR/predictions.",
    )
    parser.add_argument(
        "--verify-frozen",
        type=Path,
        help="Verify one frozen prediction directory and exit.",
    )
    parser.add_argument(
        "--availability-model",
        type=Path,
        default=DEFAULT_AVAILABILITY_MODEL,
        help="Frozen defender-availability model used only at eligible vintages.",
    )
    parser.add_argument(
        "--disable-availability-model",
        action="store_true",
        help="Do not use the historical availability prior.",
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


def rounded(value: float | None) -> float | str:
    return "" if value is None else round(value, 6)


def canonical_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return "".join(character for character in normalized.lower() if character.isalnum())


def normalized_status(value: str) -> str:
    return "_".join(value.upper().replace("/", " ").replace("-", " ").split())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def atomic_write_csv(
    path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
    temporary.replace(path)


def latest_snapshot(data_dir: Path) -> Path:
    paths = manifest_paths(data_dir)
    if not paths:
        raise RuntimeError("No injury snapshots found. Run injury_snapshot.py capture.")
    manifests = [
        (json.loads(path.read_text(encoding="utf-8"))["as_of"], path.parent)
        for path in paths
    ]
    return max(manifests, key=lambda item: item[0])[1]


def report_key(injury: dict[str, str]) -> str:
    return normalized_status(injury.get("game_status") or "") or "NO_GAME_DESIGNATION"


def practice_key(injury: dict[str, str]) -> str:
    normalized = (injury.get("practice_status") or "").upper()
    if "DID NOT PARTICIPATE" in normalized or normalized_status(normalized) == "DNP":
        return "DNP"
    if "LIMITED" in normalized:
        return "LIMITED"
    if "FULL" in normalized:
        return "FULL"
    return "NO_PRACTICE_DESIGNATION"


def load_availability_model(path: Path) -> dict[str, Any]:
    model = json.loads(path.read_text(encoding="utf-8"))
    if model.get("schema_version") != 1:
        raise ValueError(f"Unsupported availability-model schema: {path}")
    if model.get("binary_prediction_rule") != "report_status_only":
        raise ValueError("Availability model violates the frozen binary rule.")
    if model.get("retention_prediction_rule") != "report_plus_practice":
        raise ValueError("Availability model violates the frozen retention rule.")
    for group_name in ("global", "report_status", "report_plus_practice"):
        if group_name not in model:
            raise ValueError(f"Availability model is missing {group_name}.")
    parameter_groups = [model["global"]]
    parameter_groups.extend(model["report_status"].values())
    parameter_groups.extend(model["report_plus_practice"].values())
    for parameters in parameter_groups:
        for field in (
            "defensive_participation_probability",
            "expected_defense_snap_retention",
        ):
            estimate = number(parameters.get(field))
            if estimate is None or not 0 <= estimate <= 1:
                raise ValueError(f"Availability model has invalid {field}.")
    return model


def availability_model_for_vintage(
    vintage: str, path: Path | None
) -> dict[str, Any] | None:
    if path is None or vintage not in CALIBRATED_VINTAGES:
        return None
    return load_availability_model(path)


def historical_prior_allowed(injury: dict[str, str]) -> bool:
    return (injury.get("source") or "").lower() not in {
        "espn_league",
        "espn_nfl",
    }


def probability_of_playing(
    injury: dict[str, str], availability_model: dict[str, Any] | None = None
) -> tuple[float | None, str]:
    status = normalized_status(injury.get("game_status") or "")
    if status in CERTAIN_OUT_STATUSES:
        return 0.0, "deterministic_out_status"
    reported = number(injury.get("probability_playing"))
    if reported is not None and 0 <= reported <= 1:
        return reported, "provider_probability"
    if availability_model and historical_prior_allowed(injury):
        estimate = availability_model["report_status"].get(report_key(injury))
        if estimate:
            probability = number(estimate.get("defensive_participation_probability"))
            if probability is not None and 0 <= probability <= 1:
                return probability, "historical_report_status_v0"
    return None, "unknown_no_assumption"


def expected_snap_retention(
    injury: dict[str, str], availability_model: dict[str, Any] | None = None
) -> tuple[float | None, str]:
    if normalized_status(injury.get("game_status") or "") in CERTAIN_OUT_STATUSES:
        return 0.0, "deterministic_out_status"
    reported = number(injury.get("probability_playing"))
    if reported is not None and 0 <= reported <= 1:
        return None, "not_combined_with_provider_probability"
    if not availability_model or not historical_prior_allowed(injury):
        return None, "unknown_no_assumption"
    status = report_key(injury)
    practice = practice_key(injury)
    cell = availability_model["report_plus_practice"].get(f"{status}|{practice}")
    if cell:
        retention = number(cell.get("expected_defense_snap_retention"))
        if retention is not None and 0 <= retention <= 1:
            return retention, "historical_report_plus_practice_v0"
    status_estimate = availability_model["report_status"].get(status)
    if status_estimate:
        retention = number(status_estimate.get("expected_defense_snap_retention"))
        if retention is not None and 0 <= retention <= 1:
            return retention, "historical_report_status_fallback_v0"
    return None, "unknown_no_assumption"


def context_indexes(
    context: list[dict[str, str]],
) -> tuple[
    dict[tuple[str, str], list[dict[str, str]]],
    dict[tuple[str, str], list[dict[str, str]]],
]:
    by_name: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    by_espn: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for defender in context:
        team = (defender.get("team") or "").upper()
        by_name[(team, canonical_name(defender.get("player_name") or ""))].append(
            defender
        )
        espn_id = defender.get("espn_id") or ""
        if espn_id:
            by_espn[(team, espn_id)].append(defender)
    return by_name, by_espn


def match_context(
    injury: dict[str, str],
    by_name: dict[tuple[str, str], list[dict[str, str]]],
    by_espn: dict[tuple[str, str], list[dict[str, str]]],
) -> tuple[dict[str, str] | None, str]:
    team = (injury.get("team") or "").upper()
    source = (injury.get("source") or "").lower()
    source_id = injury.get("source_player_id") or ""
    if source in {"espn_league", "espn_nfl"} and source_id:
        matches = by_espn.get((team, source_id), [])
        if len(matches) == 1:
            return matches[0], "espn_id_team"
    matches = by_name.get((team, canonical_name(injury.get("player_name") or "")), [])
    if len(matches) == 1:
        return matches[0], "canonical_name_team"
    return None, "unmatched" if not matches else "ambiguous_name_team"


def depth_rank(row: dict[str, str]) -> int | None:
    value = number(row.get("depth_rank"))
    return int(value) if value is not None else None


def choose_replacement(
    defender: dict[str, str],
    context: list[dict[str, str]],
    unavailable_names: set[tuple[str, str]],
) -> dict[str, str] | None:
    team = defender.get("team") or ""
    role = defender.get("role") or ""
    current_rank = depth_rank(defender)
    candidates = []
    for candidate in context:
        if candidate.get("team") != team or candidate.get("role") != role:
            continue
        if candidate.get("source_player_id") == defender.get("source_player_id"):
            continue
        if (team, canonical_name(candidate.get("player_name") or "")) in unavailable_names:
            continue
        candidate_rank = depth_rank(candidate)
        if candidate_rank is None:
            continue
        if current_rank is not None and candidate_rank <= current_rank:
            continue
        if candidate.get("roster_status") != "ACT":
            continue
        candidates.append((candidate_rank, candidate.get("player_name") or "", candidate))
    return min(candidates, default=(0, "", None), key=lambda item: (item[0], item[1]))[2]


def build_exposures(
    snapshot_id: str,
    as_of: str,
    injuries: list[dict[str, str]],
    context: list[dict[str, str]],
    availability_model: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    defensive_injuries = [
        injury for injury in injuries if (injury.get("side") or "").lower() == "defense"
    ]
    by_name, by_espn = context_indexes(context)
    unavailable_names = {
        ((injury.get("team") or "").upper(), canonical_name(injury.get("player_name") or ""))
        for injury in defensive_injuries
        if probability_of_playing(injury, availability_model)[0] == 0
    }
    exposures: list[dict[str, Any]] = []
    for injury in defensive_injuries:
        probability, probability_source = probability_of_playing(
            injury, availability_model
        )
        retention, retention_source = expected_snap_retention(
            injury, availability_model
        )
        defender, match_method = match_context(injury, by_name, by_espn)
        healthy_share = number(defender.get("prior_defense_snap_share_4g")) if defender else None
        absence_probability = None if probability is None else 1 - probability
        absence_capacity = (
            absence_probability * healthy_share
            if absence_probability is not None and healthy_share is not None
            else None
        )
        expected_lost_fraction = None if retention is None else 1 - retention
        expected_lost_capacity = (
            expected_lost_fraction * healthy_share
            if expected_lost_fraction is not None and healthy_share is not None
            else None
        )
        replacement = (
            choose_replacement(defender, context, unavailable_names) if defender else None
        )
        exposures.append(
            {
                "snapshot_id": snapshot_id,
                "as_of": as_of,
                "source": injury.get("source") or "",
                "source_player_id": injury.get("source_player_id") or "",
                "player_name": injury.get("player_name") or "",
                "team": (injury.get("team") or "").upper(),
                "reported_role": injury.get("role") or "",
                "game_status": injury.get("game_status") or "",
                "practice_status": injury.get("practice_status") or "",
                "probability_playing": rounded(probability),
                "probability_source": probability_source,
                "availability_known": "yes" if probability is not None else "no",
                "availability_model_version": (
                    availability_model.get("model_version", "")
                    if availability_model
                    else ""
                ),
                "context_match_method": match_method,
                "context_player_id": defender.get("source_player_id") if defender else "",
                "normalized_role": (
                    defender.get("role") if defender else injury.get("role") or ""
                ),
                "roster_status": defender.get("roster_status") if defender else "",
                "depth_position": defender.get("depth_position") if defender else "",
                "depth_rank": defender.get("depth_rank") if defender else "",
                "healthy_snap_share_4g": rounded(healthy_share),
                "absence_probability": rounded(absence_probability),
                "absence_snap_capacity_lower_bound": rounded(absence_capacity),
                "expected_defense_snap_retention": rounded(retention),
                "retention_source": retention_source,
                "expected_lost_snap_fraction": rounded(expected_lost_fraction),
                "expected_lost_snap_capacity": rounded(expected_lost_capacity),
                "replacement_player": replacement.get("player_name") if replacement else "",
                "replacement_depth_rank": replacement.get("depth_rank") if replacement else "",
                "replacement_roster_status": (
                    replacement.get("roster_status") if replacement else ""
                ),
                "replacement_prior_snap_share_4g": (
                    replacement.get("prior_defense_snap_share_4g") if replacement else ""
                ),
                "quality_gap_status": "not_estimated",
            }
        )
    exposures.sort(key=lambda row: (row["team"], row["normalized_role"], row["player_name"]))
    return exposures


def build_unit_burdens(
    snapshot_id: str, as_of: str, exposures: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for exposure in exposures:
        groups[(exposure["team"], exposure["normalized_role"])].append(exposure)
    rows = []
    for (team, role), group in sorted(groups.items()):
        known = [row for row in group if row["availability_known"] == "yes"]
        capacities = [
            value
            for row in group
            if (
                value := number(row.get("absence_snap_capacity_lower_bound"))
            )
            is not None
        ]
        expected_capacities = [
            value
            for row in group
            if (value := number(row.get("expected_lost_snap_capacity"))) is not None
        ]
        starters = sum(
            1
            for row in group
            if number(row.get("depth_rank")) == 1
            and (
                number(row.get("expected_lost_snap_fraction")) not in {None, 0}
                or number(row.get("absence_probability")) not in {None, 0}
            )
        )
        affected = sum(
            1
            for row in group
            if number(row.get("expected_lost_snap_fraction")) not in {None, 0}
            or number(row.get("absence_probability")) not in {None, 0}
        )
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "as_of": as_of,
                "team": team,
                "role": role,
                "injury_records": len(group),
                "matched_defenders": sum(
                    row["context_match_method"] not in {"unmatched", "ambiguous_name_team"}
                    for row in group
                ),
                "known_availability": len(known),
                "unknown_availability": len(group) - len(known),
                "projected_starters_affected": starters,
                "absence_snap_capacity_lower_bound": (
                    rounded(sum(capacities)) if capacities else ""
                ),
                "expected_lost_snap_capacity": (
                    rounded(sum(expected_capacities))
                    if expected_capacities
                    else ""
                ),
                "cluster_flag": "yes" if affected >= 2 else "no",
                "interpretation": (
                    "Structural availability burden only; replacement quality and "
                    "fantasy-point effect are not estimated."
                ),
            }
        )
    return rows


def build(
    snapshot_dir: Path,
    output_dir: Path,
    availability_model_path: Path | None = DEFAULT_AVAILABILITY_MODEL,
) -> dict[str, Any]:
    errors = verify_snapshot(snapshot_dir)
    if errors:
        raise RuntimeError("Snapshot verification failed: " + "; ".join(errors))
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    availability_model = availability_model_for_vintage(
        str(manifest.get("vintage") or ""), availability_model_path
    )
    injuries = read_csv(snapshot_dir / "normalized" / "injuries.csv")
    context_path = snapshot_dir / "normalized" / "defensive-context.csv"
    context = read_csv(context_path) if context_path.exists() else []
    exposures = build_exposures(
        manifest["snapshot_id"],
        manifest["as_of"],
        injuries,
        context,
        availability_model,
    )
    burdens = build_unit_burdens(manifest["snapshot_id"], manifest["as_of"], exposures)
    atomic_write_csv(output_dir / "defender-exposures.csv", EXPOSURE_FIELDS, exposures)
    atomic_write_csv(output_dir / "unit-burdens.csv", UNIT_FIELDS, burdens)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_snapshot": manifest["snapshot_id"],
        "input_as_of": manifest["as_of"],
        "input_snapshot_manifest_sha256": sha256_file(
            snapshot_dir / "manifest.json"
        ),
        "defensive_injury_records": len(exposures),
        "matched_defenders": sum(
            row["context_match_method"] not in {"unmatched", "ambiguous_name_team"}
            for row in exposures
        ),
        "known_availability_records": sum(
            row["availability_known"] == "yes" for row in exposures
        ),
        "calibrated_availability_records": sum(
            row["probability_source"] == "historical_report_status_v0"
            for row in exposures
        ),
        "calibrated_retention_records": sum(
            str(row["retention_source"]).startswith("historical_")
            for row in exposures
        ),
        "availability_model_status": (
            "active"
            if availability_model
            else (
                "disabled_by_configuration"
                if availability_model_path is None
                else "disabled_for_vintage"
            )
        ),
        "availability_model_version": (
            availability_model.get("model_version", "")
            if availability_model
            else ""
        ),
        "availability_model_sha256": (
            sha256_file(availability_model_path)
            if availability_model and availability_model_path is not None
            else ""
        ),
        "unit_burdens": len(burdens),
        "point_adjustment_status": "not_estimated",
        "limitations": [
            "Historical availability calibration is used only at final-status/inactive vintages and only for injury-listed defenders.",
            "Binary participation uses report status only; practice status enters expected snap retention, where it improved held-out MAE only slightly.",
            "Provider play probabilities are preserved but not combined with the historical retention model.",
            "Absence capacity is not defender quality or starter-minus-replacement quality.",
            "No fantasy-point adjustment is produced before validation.",
        ],
    }
    atomic_write_json(output_dir / "summary.json", summary)
    return summary


def write_prediction_manifest(
    output_dir: Path, summary: dict[str, Any]
) -> dict[str, Any]:
    files = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "prediction-manifest.json":
            files.append(
                {
                    "path": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "schema_version": 1,
        "prediction_id": summary["input_snapshot"],
        "generated_at": summary["generated_at"],
        "input_as_of": summary["input_as_of"],
        "input_snapshot_manifest_sha256": summary[
            "input_snapshot_manifest_sha256"
        ],
        "availability_model_version": summary["availability_model_version"],
        "availability_model_sha256": summary["availability_model_sha256"],
        "point_adjustment_status": summary["point_adjustment_status"],
        "files": files,
    }
    atomic_write_json(output_dir / "prediction-manifest.json", manifest)
    return manifest


def verify_frozen_prediction(prediction_dir: Path) -> list[str]:
    manifest_path = prediction_dir / "prediction-manifest.json"
    if not manifest_path.exists():
        return [f"missing prediction manifest: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"invalid prediction manifest {manifest_path}: {error}"]
    errors = []
    if manifest.get("schema_version") != 1:
        errors.append(f"unsupported prediction schema: {manifest_path}")
    if manifest.get("prediction_id") != prediction_dir.name:
        errors.append(f"prediction ID does not match directory: {prediction_dir}")
    declared = {"prediction-manifest.json"}
    for record in manifest.get("files", []):
        relative = Path(str(record.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
            errors.append(f"unsafe frozen prediction path: {relative}")
            continue
        declared.add(relative.as_posix())
        path = prediction_dir / relative
        if not path.is_file():
            errors.append(f"missing frozen prediction file: {path}")
            continue
        if path.stat().st_size != record.get("bytes"):
            errors.append(f"byte count mismatch: {path}")
        if sha256_file(path) != record.get("sha256"):
            errors.append(f"sha256 mismatch: {path}")
    actual = {
        path.relative_to(prediction_dir).as_posix()
        for path in prediction_dir.rglob("*")
        if path.is_file()
    }
    if extras := sorted(actual - declared):
        errors.append(f"undeclared frozen prediction files: {', '.join(extras)}")
    if missing := sorted(declared - actual):
        errors.append(f"declared frozen prediction files absent: {', '.join(missing)}")
    return errors


def freeze_prediction(
    data_dir: Path,
    snapshot_dir: Path,
    availability_model_path: Path | None,
) -> tuple[dict[str, Any], Path]:
    parent = data_dir / "predictions"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / snapshot_dir.name
    if destination.exists():
        raise FileExistsError(f"Frozen prediction already exists: {destination}")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{snapshot_dir.name}-", dir=parent)
    )
    try:
        summary = build(snapshot_dir, staging, availability_model_path)
        write_prediction_manifest(staging, summary)
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return summary, destination


def main() -> int:
    args = parse_args()
    try:
        if args.verify_frozen:
            errors = verify_frozen_prediction(args.verify_frozen)
            if errors:
                for error in errors:
                    print(f"[invalid] {error}", file=sys.stderr)
                return 1
            print(f"[verified prediction] {args.verify_frozen}")
            return 0
        snapshot_dir = args.snapshot or latest_snapshot(args.data_dir)
        availability_model_path = (
            None if args.disable_availability_model else args.availability_model
        )
        if args.freeze:
            if args.output_dir:
                raise ValueError("--freeze and --output-dir cannot be combined.")
            summary, output_dir = freeze_prediction(
                args.data_dir, snapshot_dir, availability_model_path
            )
        else:
            output_dir = args.output_dir or args.data_dir / "current"
            summary = build(snapshot_dir, output_dir, availability_model_path)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"[injury signal] snapshot={summary['input_snapshot']} "
        f"defensive injuries={summary['defensive_injury_records']} "
        f"matched={summary['matched_defenders']} "
        f"known availability={summary['known_availability_records']}"
    )
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
