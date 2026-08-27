# SPDX-License-Identifier: MPL-2.0
import json
import tempfile
import unittest
from pathlib import Path

from scripts.injury_signal import (
    DEFAULT_AVAILABILITY_MODEL,
    availability_model_for_vintage,
    build_exposures,
    build_unit_burdens,
    probability_of_playing,
    verify_frozen_prediction,
    write_prediction_manifest,
)


def availability_model() -> dict:
    return {
        "model_version": "test-v0",
        "report_status": {
            "QUESTIONABLE": {
                "defensive_participation_probability": 0.6,
                "expected_defense_snap_retention": 0.5,
            }
        },
        "report_plus_practice": {
            "QUESTIONABLE|LIMITED": {
                "defensive_participation_probability": 0.4,
                "expected_defense_snap_retention": 0.4,
            }
        },
    }


def defender(
    name: str,
    player_id: str,
    depth_rank: int,
    snap_share: float,
) -> dict[str, str]:
    return {
        "source_player_id": player_id,
        "espn_id": "",
        "player_name": name,
        "team": "GB",
        "role": "S",
        "roster_status": "ACT",
        "depth_position": "FS",
        "depth_rank": str(depth_rank),
        "prior_defense_snap_share_4g": str(snap_share),
    }


class InjurySignalTests(unittest.TestCase):
    def test_frozen_prediction_manifest_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prediction_dir = Path(temporary) / "snapshot-id"
            prediction_dir.mkdir()
            (prediction_dir / "defender-exposures.csv").write_text(
                "snapshot_id\nsnapshot-id\n", encoding="utf-8"
            )
            (prediction_dir / "unit-burdens.csv").write_text(
                "snapshot_id\nsnapshot-id\n", encoding="utf-8"
            )
            (prediction_dir / "summary.json").write_text("{}\n", encoding="utf-8")
            summary = {
                "input_snapshot": "snapshot-id",
                "generated_at": "2026-08-25T19:00:00Z",
                "input_as_of": "2026-08-25T18:59:00Z",
                "input_snapshot_manifest_sha256": "a" * 64,
                "availability_model_version": "",
                "availability_model_sha256": "",
                "point_adjustment_status": "not_estimated",
            }
            manifest = write_prediction_manifest(prediction_dir, summary)

            self.assertEqual(manifest["prediction_id"], "snapshot-id")
            self.assertEqual(verify_frozen_prediction(prediction_dir), [])

            (prediction_dir / "summary.json").write_text(
                json.dumps({"tampered": True}), encoding="utf-8"
            )
            errors = verify_frozen_prediction(prediction_dir)

            self.assertTrue(any("sha256 mismatch" in error for error in errors))

    def test_frozen_model_is_gated_to_final_information_vintages(self) -> None:
        self.assertIsNone(
            availability_model_for_vintage("pre_practice", DEFAULT_AVAILABILITY_MODEL)
        )
        active = availability_model_for_vintage(
            "final_status", DEFAULT_AVAILABILITY_MODEL
        )

        self.assertEqual(active["model_version"], "defender-availability-v0")
        for cell_key, cell in active["report_plus_practice"].items():
            report_status = cell_key.split("|", maxsplit=1)[0]
            participation = active["report_status"][report_status][
                "defensive_participation_probability"
            ]
            self.assertLessEqual(
                cell["expected_defense_snap_retention"], participation
            )

    def test_does_not_invent_questionable_probability(self) -> None:
        probability, source = probability_of_playing(
            {"game_status": "Questionable", "probability_playing": ""}
        )
        self.assertIsNone(probability)
        self.assertEqual(source, "unknown_no_assumption")

    def test_provider_probability_drives_absence_capacity_lower_bound(self) -> None:
        injuries = [
            {
                "source": "fantasypros",
                "source_player_id": "7",
                "player_name": "Starting Safety",
                "team": "GB",
                "side": "defense",
                "role": "S",
                "game_status": "Questionable",
                "practice_status": "Limited",
                "probability_playing": "0.25",
            }
        ]
        context = [
            defender("Starting Safety", "00-1", 1, 0.8),
            defender("Backup Safety", "00-2", 2, 0.3),
        ]

        exposures = build_exposures(
            "snapshot", "as-of", injuries, context, availability_model()
        )

        self.assertEqual(len(exposures), 1)
        self.assertEqual(exposures[0]["context_match_method"], "canonical_name_team")
        self.assertEqual(exposures[0]["absence_probability"], 0.75)
        self.assertEqual(exposures[0]["absence_snap_capacity_lower_bound"], 0.6)
        self.assertEqual(exposures[0]["expected_defense_snap_retention"], "")
        self.assertEqual(
            exposures[0]["retention_source"],
            "not_combined_with_provider_probability",
        )
        self.assertEqual(exposures[0]["replacement_player"], "Backup Safety")
        self.assertEqual(exposures[0]["quality_gap_status"], "not_estimated")

    def test_official_out_overrides_provider_probability(self) -> None:
        probability, source = probability_of_playing(
            {"game_status": "Out", "probability_playing": "0.8"},
            availability_model(),
        )

        self.assertEqual(probability, 0.0)
        self.assertEqual(source, "deterministic_out_status")

    def test_historical_prior_estimates_participation_and_lost_snap_capacity(self) -> None:
        injuries = [
            {
                "source": "official",
                "source_player_id": "",
                "player_name": "Starting Safety",
                "team": "GB",
                "side": "defense",
                "role": "S",
                "game_status": "Questionable",
                "practice_status": "Limited Participation in Practice",
                "probability_playing": "",
            }
        ]
        context = [defender("Starting Safety", "00-1", 1, 0.8)]

        exposure = build_exposures(
            "snapshot", "as-of", injuries, context, availability_model()
        )[0]

        self.assertEqual(exposure["probability_playing"], 0.6)
        self.assertEqual(exposure["probability_source"], "historical_report_status_v0")
        self.assertEqual(exposure["absence_snap_capacity_lower_bound"], 0.32)
        self.assertEqual(exposure["expected_defense_snap_retention"], 0.4)
        self.assertEqual(
            exposure["retention_source"], "historical_report_plus_practice_v0"
        )
        self.assertEqual(exposure["expected_lost_snap_capacity"], 0.48)
        self.assertEqual(exposure["availability_model_version"], "test-v0")

    def test_espn_watchlist_status_does_not_receive_official_report_prior(self) -> None:
        injuries = [
            {
                "source": "espn_nfl",
                "source_player_id": "4428633",
                "player_name": "Different Display Name",
                "team": "GB",
                "side": "defense",
                "role": "S",
                "game_status": "Questionable",
                "practice_status": "",
                "probability_playing": "",
            }
        ]
        context = [
            {
                **defender("Roster Name", "00-1", 1, 0.8),
                "espn_id": "4428633",
            }
        ]

        exposure = build_exposures(
            "snapshot", "as-of", injuries, context, availability_model()
        )[0]

        self.assertEqual(exposure["context_match_method"], "espn_id_team")
        self.assertEqual(exposure["probability_playing"], "")
        self.assertEqual(exposure["probability_source"], "unknown_no_assumption")
        self.assertEqual(exposure["expected_defense_snap_retention"], "")

    def test_out_status_is_known_but_missing_snap_history_stays_unquantified(self) -> None:
        injuries = [
            {
                "source": "official",
                "source_player_id": "",
                "player_name": "Rookie Corner",
                "team": "GB",
                "side": "defense",
                "role": "CB",
                "game_status": "Out",
                "practice_status": "DNP",
                "probability_playing": "",
            }
        ]
        context = [
            {
                **defender("Rookie Corner", "00-3", 1, 0.0),
                "role": "CB",
                "depth_position": "LCB",
                "prior_defense_snap_share_4g": "",
            }
        ]

        exposure = build_exposures("snapshot", "as-of", injuries, context)[0]

        self.assertEqual(exposure["probability_playing"], 0.0)
        self.assertEqual(exposure["absence_probability"], 1.0)
        self.assertEqual(exposure["absence_snap_capacity_lower_bound"], "")
        self.assertEqual(exposure["expected_defense_snap_retention"], 0.0)
        self.assertEqual(exposure["expected_lost_snap_fraction"], 1.0)

    def test_unit_cluster_requires_two_known_affected_defenders(self) -> None:
        exposures = [
            {
                "team": "GB",
                "normalized_role": "S",
                "availability_known": "yes",
                "context_match_method": "canonical_name_team",
                "depth_rank": "1",
                "absence_probability": 1.0,
                "absence_snap_capacity_lower_bound": 0.8,
                "expected_lost_snap_fraction": 1.0,
                "expected_lost_snap_capacity": 0.8,
            },
            {
                "team": "GB",
                "normalized_role": "S",
                "availability_known": "yes",
                "context_match_method": "canonical_name_team",
                "depth_rank": "2",
                "absence_probability": 0.5,
                "absence_snap_capacity_lower_bound": 0.2,
                "expected_lost_snap_fraction": 0.6,
                "expected_lost_snap_capacity": 0.25,
            },
        ]

        burden = build_unit_burdens("snapshot", "as-of", exposures)[0]

        self.assertEqual(burden["absence_snap_capacity_lower_bound"], 1.0)
        self.assertEqual(burden["expected_lost_snap_capacity"], 1.05)
        self.assertEqual(burden["cluster_flag"], "yes")
        self.assertEqual(burden["projected_starters_affected"], 1)


if __name__ == "__main__":
    unittest.main()
