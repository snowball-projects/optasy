# Copyright 2026 snowball
# SPDX-License-Identifier: Apache-2.0
import unittest

from scripts.calibrate_defender_availability import (
    bootstrap_mean_ci,
    build_records,
    fit_predictors,
    practice_category,
    prior_baseline,
    report_category,
)


def snap(season: int, week: int, defense_snaps: int, defense_pct: float) -> dict[str, str]:
    return {
        "season": str(season),
        "week": str(week),
        "game_type": "REG",
        "team": "GB",
        "pfr_player_id": "TestPl00",
        "defense_snaps": str(defense_snaps),
        "defense_pct": str(defense_pct),
    }


def schedule(gameday: str = "2024-09-15", gametime: str = "13:00") -> list[dict[str, str]]:
    return [
        {
            "season": "2024",
            "game_type": "REG",
            "week": "2",
            "gameday": gameday,
            "gametime": gametime,
            "away_team": "GB",
            "home_team": "TEN",
        }
    ]


class DefenderAvailabilityTests(unittest.TestCase):
    def test_block_bootstrap_preserves_constant_mean(self) -> None:
        interval = bootstrap_mean_ci([0.25, 0.25, 0.25], ["w1", "w1", "w2"])

        self.assertEqual(interval, {"mean": 0.25, "lower_95": 0.25, "upper_95": 0.25})

    def test_categories_are_explicit_and_stable(self) -> None:
        self.assertEqual(report_category("Questionable"), "QUESTIONABLE")
        self.assertEqual(report_category(""), "NO_GAME_DESIGNATION")
        self.assertEqual(practice_category("Did Not Participate In Practice"), "DNP")
        self.assertEqual(practice_category("Limited Participation"), "LIMITED")
        self.assertEqual(practice_category("Full Participation"), "FULL")

    def test_prior_baseline_uses_only_last_four_prior_appearances(self) -> None:
        history = [
            (2023, 16, 0.1),
            (2023, 17, 0.2),
            (2024, 1, 0.3),
            (2024, 2, 0.4),
            (2024, 3, 0.5),
            (2024, 4, 0.9),
        ]

        baseline, games = prior_baseline(history, 2024, 4)

        self.assertEqual(games, 4)
        self.assertAlmostEqual(baseline or 0, 0.35)

    def test_record_target_is_defensive_participation_and_is_temporal(self) -> None:
        injuries = {
            2024: [
                {
                    "game_type": "REG",
                    "week": "2",
                    "team": "GB",
                    "gsis_id": "00-0000001",
                    "position": "CB",
                    "full_name": "Test Player",
                    "report_status": "Questionable",
                    "practice_status": "Limited Participation",
                    "report_primary_injury": "Hamstring",
                    "date_modified": "2024-09-10T20:00:00Z",
                }
            ]
        }
        rosters = {
            2024: [
                {
                    "team": "GB",
                    "gsis_id": "00-0000001",
                    "pfr_id": "TestPl00",
                }
            ]
        }
        snaps = {
            2023: [snap(2023, 17, 30, 0.5)],
            2024: [
                snap(2024, 1, 36, 0.6),
                snap(2024, 2, 18, 0.3),
                snap(2024, 3, 50, 0.9),
            ],
        }

        records = build_records([2024], injuries, rosters, snaps, schedule())

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["played_defensive_snap"], 1)
        self.assertEqual(record["healthy_baseline_games"], 2)
        self.assertAlmostEqual(record["healthy_defense_snap_share_4g"], 0.55)
        self.assertAlmostEqual(record["defense_snap_retention"], 0.545455)
        self.assertEqual(record["information_available_pre_kickoff"], 1)

    def test_post_kickoff_injury_timestamp_is_excluded_and_counted(self) -> None:
        injuries = {
            2024: [
                {
                    "game_type": "REG",
                    "week": "2",
                    "team": "GB",
                    "gsis_id": "00-0000001",
                    "position": "CB",
                    "date_modified": "2024-09-15T20:00:00Z",
                }
            ]
        }
        rosters = {
            2024: [
                {
                    "team": "GB",
                    "gsis_id": "00-0000001",
                    "pfr_id": "TestPl00",
                }
            ]
        }

        timing_audit: dict[str, int] = {}
        records = build_records(
            [2024], injuries, rosters, {2024: []}, schedule(), timing_audit
        )

        self.assertEqual(records, [])
        self.assertEqual(timing_audit["post_kickoff_source_rows_excluded"], 1)
        self.assertEqual(timing_audit["pre_kickoff_source_rows"], 0)

    def test_practice_status_adds_shrunk_information_within_report_status(self) -> None:
        train = []
        for practice_status, plays, retention in (
            ("FULL", 18, 0.9),
            ("DNP", 2, 0.2),
        ):
            for index in range(20):
                train.append(
                    {
                        "report_status": "QUESTIONABLE",
                        "practice_status": practice_status,
                        "played_defensive_snap": int(index < plays),
                        "defense_snap_retention": retention,
                    }
                )

        (
            status_predict,
            model_predict,
            status_retention_predict,
            retention_predict,
        ) = fit_predictors(train)
        full = {"report_status": "QUESTIONABLE", "practice_status": "FULL"}
        dnp = {"report_status": "QUESTIONABLE", "practice_status": "DNP"}

        self.assertAlmostEqual(status_predict(full), status_predict(dnp))
        self.assertAlmostEqual(
            status_retention_predict(full), status_retention_predict(dnp)
        )
        self.assertGreater(model_predict(full), model_predict(dnp))
        self.assertGreater(retention_predict(full), retention_predict(dnp))
        self.assertLessEqual(retention_predict(full), status_predict(full))
        self.assertLessEqual(retention_predict(dnp), status_predict(dnp))


if __name__ == "__main__":
    unittest.main()
