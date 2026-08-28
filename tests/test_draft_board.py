# Copyright 2026 snowball
# SPDX-License-Identifier: Apache-2.0
import csv
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.draft_board import (
    CALIBRATION_RANKINGS,
    CalibrationSample,
    EspnCredentials,
    LeagueContext,
    archive_live_decision,
    availability_estimate,
    build_live_rankings,
    build_source_changes,
    calibration_path,
    conditional_availability_estimate,
    draft_state_sha256,
    freeze_draft_sources,
    load_calibration_samples,
    reference_path,
    refresh,
    resolve_frozen_draft_sources,
    starter_replacement_levels,
    user_draft_state,
    user_pick_sequence,
    weighted_quantile,
)


def context(team_count: int = 12) -> LeagueContext:
    return LeagueContext(
        season=2026,
        league_id="test",
        team_count=team_count,
        user_pick_position=5,
        draft_rounds=15,
        allowed_positions=frozenset({"QB", "RB", "WR", "TE", "K"}),
        starter_counts=(("QB", 1), ("RB", 1), ("WR", 1), ("TE", 1)),
        flex_count=1,
        position_maximums=(("QB", 1), ("RB", 8), ("WR", 8), ("TE", 3), ("K", 3)),
        lineup_counts=(("QB", 1), ("RB", 1), ("WR", 1), ("TE", 1), ("K", 1)),
    )


def draft_payload(completed_through: int) -> dict:
    pick_order = [1, 5, 8, 9, 2, 10, 6, 7, 3, 11, 12, 4]
    picks = []
    for overall_pick in range(1, 181):
        round_index = (overall_pick - 1) // 12
        round_pick = (overall_pick - 1) % 12
        order = pick_order if round_index % 2 == 0 else list(reversed(pick_order))
        team_id = order[round_pick]
        player_id = 1_000 + overall_pick if overall_pick <= completed_through else -1
        picks.append(
            {
                "overallPickNumber": overall_pick,
                "teamId": team_id,
                "playerId": player_id,
            }
        )
    return {
        "settings": {"draftSettings": {"pickOrder": pick_order}},
        "draftDetail": {"picks": picks},
    }


def board_row(
    espn_id: int,
    player: str,
    position: str,
    vorp: float | None,
    *,
    available: str = "yes",
    drafted_overall: int | str = "",
    drafted_by_team_id: int | str = "",
    consensus_rank: int = 1,
) -> dict:
    return {
        "available": available,
        "player": player,
        "team": "TST",
        "position": position,
        "espn_projected_points": 250,
        "value_over_replacement": vorp,
        "replacement_rank": 12,
        "replacement_points": 200,
        "consensus_rank": consensus_rank,
        "espn_ppr_rank": consensus_rank,
        "espn_adp": consensus_rank,
        "expert_rank_sd": 2,
        "injury_status": "",
        "injured": "no",
        "espn_id": espn_id,
        "snapshot_at": "2026-09-07T23:00:00Z",
        "drafted_overall": drafted_overall,
        "drafted_by_team_id": drafted_by_team_id,
    }


class DraftBoardTests(unittest.TestCase):
    def test_refresh_refuses_same_second_snapshot_collision(self) -> None:
        rankings_output = io.StringIO()
        writer = csv.DictWriter(
            rankings_output,
            fieldnames=["page_type", "fp_page", "scrape_date"],
        )
        writer.writeheader()
        for _ in range(200):
            writer.writerow(
                {
                    "page_type": "redraft-overall",
                    "fp_page": "/nfl/rankings/ppr-cheatsheets.php",
                    "scrape_date": "2026-08-25",
                }
            )
        rankings_text = rankings_output.getvalue()
        credentials = EspnCredentials("test", "placeholder", "placeholder")
        captured = ("20260825T180000Z", "2026-08-25T18:00:00+00:00")

        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            with (
                patch(
                    "scripts.draft_board.refresh_reference",
                    return_value=data_dir / "reference.csv",
                ),
                patch(
                    "scripts.draft_board.ensure_calibration_references",
                    return_value={},
                ),
                patch(
                    "scripts.draft_board.fetch_espn_players",
                    side_effect=[
                        {"players": [{"version": "first"}]},
                        {"players": [{"version": "second"}]},
                    ],
                ),
                patch(
                    "scripts.draft_board.fetch_espn_draft",
                    side_effect=[{"version": "first"}, {"version": "second"}],
                ),
                patch(
                    "scripts.draft_board.download_text",
                    side_effect=[rankings_text, rankings_text],
                ),
                patch("scripts.draft_board.snapshot_timestamp", return_value=captured),
            ):
                snapshot = refresh(context(), credentials, data_dir, False)
                original_files = {
                    path.name: path.read_bytes() for path in snapshot.iterdir()
                }

                with self.assertRaisesRegex(FileExistsError, "cannot be overwritten"):
                    refresh(context(), credentials, data_dir, False)

            self.assertEqual(
                {path.name: path.read_bytes() for path in snapshot.iterdir()},
                original_files,
            )
            self.assertEqual(
                list(snapshot.parent.glob(f".{snapshot.name}-*")),
                [],
            )

    def test_user_pick_sequence_matches_fifth_slot_snake(self) -> None:
        self.assertEqual(user_pick_sequence(context())[:6], [5, 20, 29, 44, 53, 68])

    def test_weighted_quantile_uses_weights(self) -> None:
        values = [(1, 0.1), (5, 0.2), (9, 0.7)]
        self.assertEqual(weighted_quantile(values, 0.5), 9)
        self.assertEqual(weighted_quantile(values, 0.2), 5)

    def test_availability_declines_for_later_target_pick(self) -> None:
        samples = [
            CalibrationSample(2024, "RB", 1, 1 + residual, residual)
            for residual in (-2, 0, 2, 5)
        ] + [
            CalibrationSample(2024, "WR", 1, 1 + residual, residual)
            for residual in (-1, 1, 4, 8)
        ]
        at_five = availability_estimate(4, 5, "RB", samples)
        at_ten = availability_estimate(4, 10, "RB", samples)
        self.assertGreater(at_five["availability"], at_ten["availability"])
        self.assertGreater(at_five["position_weight"], 0)
        self.assertGreaterEqual(at_five["pick_p25"], 1)

    def test_live_availability_matches_opening_estimate_before_draft(self) -> None:
        samples = [
            CalibrationSample(2024, "RB", 1, 1 + residual, residual)
            for residual in (-2, 0, 2, 5)
        ] + [
            CalibrationSample(2024, "WR", 1, 1 + residual, residual)
            for residual in (-1, 1, 4, 8)
        ]
        opening = availability_estimate(4, 5, "RB", samples)
        live = conditional_availability_estimate(
            4,
            observed_through_pick=0,
            target_pick=5,
            position="RB",
            samples=samples,
        )

        self.assertEqual(live["availability"], opening["availability"])
        self.assertEqual(live["conditioning_samples"], len(samples))

    def test_live_availability_conditions_on_unexpected_survival(self) -> None:
        samples = [
            CalibrationSample(2024, "WR", 10, 10 + residual, residual)
            for residual in (-5, 0, 5, 10)
        ]
        unconditional = availability_estimate(10, 15, "WR", samples)
        conditional = conditional_availability_estimate(
            10, observed_through_pick=10, target_pick=15, position="WR", samples=samples
        )

        self.assertGreater(
            conditional["availability"], unconditional["availability"]
        )
        self.assertEqual(conditional["conditioning_samples"], 2)

    def test_replacement_levels_allocate_flex_after_direct_starters(self) -> None:
        rows = []
        players = {
            "QB": [30, 20, 10],
            "RB": [50, 40, 30, 20],
            "WR": [60, 35, 25, 15],
            "TE": [22, 18, 12],
        }
        player_id = 1
        for position, projections in players.items():
            for projection in projections:
                rows.append(
                    {
                        "position": position,
                        "espn_projected_points": projection,
                        "espn_id": player_id,
                    }
                )
                player_id += 1

        levels = starter_replacement_levels(context(team_count=2), rows)

        self.assertEqual(levels["QB"], {"rank": 2, "points": 20})
        self.assertEqual(levels["RB"], {"rank": 3, "points": 30})
        self.assertEqual(levels["WR"], {"rank": 3, "points": 25})
        self.assertEqual(levels["TE"], {"rank": 2, "points": 18})

    def test_live_state_infers_user_team_and_detects_on_clock(self) -> None:
        state = user_draft_state(context(), draft_payload(completed_through=4))

        self.assertEqual(state["user_team_id"], 2)
        self.assertEqual(state["next_user_pick"], 5)
        self.assertTrue(state["on_clock"])
        self.assertEqual(state["picks_until_user_turn"], 0)

    def test_draft_state_changes_when_pick_ownership_is_traded(self) -> None:
        before = draft_payload(completed_through=4)
        after = draft_payload(completed_through=4)
        after["draftDetail"]["picks"][19]["teamId"] = 7

        self.assertNotEqual(draft_state_sha256(before), draft_state_sha256(after))

    def test_source_change_report_prioritizes_injury_and_news(self) -> None:
        previous = board_row(1, "Player", "WR", 80)
        previous["injury_status"] = "ACTIVE"
        previous["last_news_at"] = "2026-08-20T12:00:00+00:00"
        current = dict(previous)
        current["injury_status"] = "QUESTIONABLE"
        current["injured"] = "yes"
        current["last_news_at"] = "2026-08-25T12:00:00+00:00"
        current["espn_projected_points"] = 230

        changes = build_source_changes([previous], [current], "old", "new")

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["review_priority"], "1_injury_review")
        self.assertIn("new_player_news_timestamp", changes[0]["change_types"])
        self.assertEqual(changes[0]["projected_points_change"], -20)

    def test_frozen_source_baseline_verifies_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            data_dir = root / "draft"
            snapshot_dir = data_dir / "snapshots" / "snapshot-test"
            snapshot_dir.mkdir(parents=True)
            manifest = {"season": 2026, "league_id": "test", "captured_at": "now"}
            (snapshot_dir / "manifest.json").write_text(json.dumps(manifest))
            for filename in (
                "espn-players.json",
                "espn-draft.json",
                "dynastyprocess-rankings.csv",
            ):
                (snapshot_dir / filename).write_text("test\n")
            config_path = root / "league.yaml"
            config_path.write_text("test: true\n")

            frozen = freeze_draft_sources(
                context(), data_dir, snapshot_dir, config_path
            )

            self.assertTrue(frozen.exists())
            self.assertEqual(
                resolve_frozen_draft_sources(context(), data_dir, config_path),
                snapshot_dir,
            )
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                freeze_draft_sources(context(), data_dir, snapshot_dir, config_path)
            amended = freeze_draft_sources(
                context(),
                data_dir,
                snapshot_dir,
                config_path,
                amendment_reason="Material late injury update",
            )
            self.assertNotEqual(frozen, amended)
            self.assertTrue(frozen.exists())
            self.assertEqual(
                resolve_frozen_draft_sources(context(), data_dir, config_path),
                snapshot_dir,
            )

    def test_live_ranking_changes_when_top_player_is_drafted(self) -> None:
        payload = draft_payload(completed_through=4)
        rows = [
            board_row(1, "Top Receiver", "WR", 80, consensus_rank=2),
            board_row(2, "Next Running Back", "RB", 70, consensus_rank=3),
        ]

        _, before = build_live_rankings(context(), rows, [], payload)
        self.assertEqual(before["recommendation"]["player"], "Top Receiver")

        rows[0]["available"] = "no"
        rows[0]["drafted_overall"] = 4
        rows[0]["drafted_by_team_id"] = 9
        _, after = build_live_rankings(context(), rows, [], payload)
        self.assertEqual(after["recommendation"]["player"], "Next Running Back")

    def test_live_ranking_respects_actual_roster_position_maximum(self) -> None:
        payload = draft_payload(completed_through=19)
        payload["draftDetail"]["picks"][4]["playerId"] = 10
        rows = [
            board_row(
                10,
                "Roster Quarterback",
                "QB",
                90,
                available="no",
                drafted_overall=5,
                drafted_by_team_id=2,
            ),
            board_row(11, "Another Quarterback", "QB", 100, consensus_rank=4),
            board_row(12, "Needed Running Back", "RB", 80, consensus_rank=5),
        ]

        rankings, recommendation = build_live_rankings(context(), rows, [], payload)

        self.assertEqual(recommendation["next_user_pick"], 20)
        self.assertEqual(
            recommendation["recommendation"]["player"], "Needed Running Back"
        )
        quarterback = next(row for row in rankings if row["espn_id"] == 11)
        self.assertEqual(quarterback["eligible_for_recommendation"], "no")
        self.assertIn("position_maximum_reached", quarterback["policy_review"])

    def test_last_pick_uses_explicit_required_kicker_fallback(self) -> None:
        payload = draft_payload(completed_through=172)
        roster_rows = [
            board_row(
                20 + index,
                f"Roster {position}",
                position,
                20,
                available="no",
                drafted_overall=pick,
                drafted_by_team_id=2,
            )
            for index, (position, pick) in enumerate(
                (("QB", 5), ("RB", 20), ("WR", 29), ("TE", 44), ("RB", 53))
            )
        ]
        rows = roster_rows + [
            board_row(30, "Best Remaining Skill Player", "RB", 100),
            board_row(31, "Required Kicker", "K", None, consensus_rank=120),
        ]

        rankings, recommendation = build_live_rankings(context(), rows, [], payload)

        self.assertTrue(recommendation["on_clock"])
        self.assertEqual(recommendation["next_user_pick"], 173)
        self.assertEqual(recommendation["recommendation"]["player"], "Required Kicker")
        kicker = next(row for row in rankings if row["espn_id"] == 31)
        self.assertIn(
            "required_starter_fallback_without_projection", kicker["policy_review"]
        )

    def test_live_decision_archive_is_idempotent_for_same_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            data_dir = root / "draft"
            snapshot_dir = data_dir / "snapshots" / "frozen-test"
            snapshot_dir.mkdir(parents=True)
            (snapshot_dir / "manifest.json").write_text("{}\n")
            recommendation = {
                "on_clock": True,
                "next_user_pick": 5,
                "last_overall_pick": 4,
                "recommendation": {"player": "Top Receiver"},
            }
            live_rows = [board_row(1, "Top Receiver", "WR", 80)]
            payload = draft_payload(completed_through=4)

            first = archive_live_decision(
                data_dir, snapshot_dir, payload, live_rows, recommendation
            )
            second = archive_live_decision(
                data_dir, snapshot_dir, payload, live_rows, recommendation
            )

            self.assertEqual(first, second)
            self.assertTrue((first / "decision-state.json").exists())
            packages = list((data_dir / "decisions").glob("**/decision-state.json"))
            self.assertEqual(len(packages), 1)

    def test_calibration_loader_rejects_mixed_prediction_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            data_dir = root / "draft"
            reference = reference_path(data_dir)
            reference.parent.mkdir(parents=True)
            with reference.open("w", newline="") as output:
                writer = csv.DictWriter(
                    output,
                    fieldnames=["fantasypros_id", "espn_id"],
                )
                writer.writeheader()
                writer.writerows(
                    {"fantasypros_id": player_id, "espn_id": player_id}
                    for player_id in range(1, 61)
                )

            for season, metadata in CALIBRATION_RANKINGS.items():
                path = calibration_path(data_dir, season)
                with path.open("w", newline="") as output:
                    writer = csv.DictWriter(
                        output,
                        fieldnames=[
                            "page_type",
                            "fp_page",
                            "pos",
                            "ecr",
                            "id",
                            "scrape_date",
                        ],
                    )
                    writer.writeheader()
                    for player_id in range(1, 61):
                        date = metadata["scrape_date"]
                        if season == 2025 and player_id == 60:
                            date = "2025-09-30"
                        writer.writerow(
                            {
                                "page_type": "redraft-overall",
                                "fp_page": "/nfl/rankings/ppr-cheatsheets.php",
                                "pos": "RB",
                                "ecr": player_id,
                                "id": player_id,
                                "scrape_date": date,
                            }
                        )

            database = root / "optasy.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE draft_picks "
                    "(season INTEGER, player_id INTEGER, overall_pick INTEGER)"
                )
                connection.executemany(
                    "INSERT INTO draft_picks VALUES (?, ?, ?)",
                    [
                        (season, player_id, player_id)
                        for season in CALIBRATION_RANKINGS
                        for player_id in range(1, 61)
                    ],
                )

            with self.assertRaisesRegex(RuntimeError, "calibration dates"):
                load_calibration_samples(context(), data_dir, database)


if __name__ == "__main__":
    unittest.main()
