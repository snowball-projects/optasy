import csv
import gzip
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.injury_snapshot import (
    RawArtifact,
    SnapshotSpec,
    build_snapshot,
    normalize_espn_players,
    normalize_espn_nfl_injuries,
    normalize_fantasypros_injuries,
    normalize_fantasypros_projections,
    normalize_nflverse_context,
    parse_timestamp,
    read_generic_injuries,
    verify_snapshot,
)


def espn_payload() -> dict:
    return {
        "players": [
            {
                "player": {
                    "id": 101,
                    "fullName": "Deep Receiver",
                    "proTeamId": 8,
                    "defaultPositionId": 3,
                    "injured": True,
                    "injuryStatus": "QUESTIONABLE",
                    "stats": [
                        {
                            "seasonId": 2026,
                            "scoringPeriodId": 1,
                            "statSourceId": 1,
                            "statSplitTypeId": 1,
                            "appliedTotal": 17.25,
                        },
                        {
                            "seasonId": 2026,
                            "scoringPeriodId": 0,
                            "statSourceId": 1,
                            "statSplitTypeId": 0,
                            "appliedTotal": 280.5,
                        },
                    ],
                }
            },
            {
                "player": {
                    "id": 202,
                    "fullName": "Healthy Runner",
                    "proTeamId": 9,
                    "defaultPositionId": 2,
                    "injured": False,
                    "injuryStatus": "ACTIVE",
                    "stats": [
                        {
                            "seasonId": 2026,
                            "scoringPeriodId": 1,
                            "statSourceId": 1,
                            "statSplitTypeId": 1,
                            "appliedTotal": 14.0,
                        }
                    ],
                }
            },
        ]
    }


class InjurySnapshotTests(unittest.TestCase):
    def test_normalizes_all_team_espn_defender_injuries_without_active_noise(self) -> None:
        payload = {
            "injuries": [
                {
                    "injuries": [
                        {
                            "id": "634539",
                            "status": "Questionable",
                            "date": "2026-08-23T02:45Z",
                            "details": {"type": "Ribs"},
                            "athlete": {
                                "displayName": "Dadrion Taylor-Demerson",
                                "position": {"abbreviation": "S"},
                                "team": {"abbreviation": "ARI"},
                                "links": [
                                    {
                                        "href": (
                                            "https://www.espn.com/nfl/player/_/id/"
                                            "4428633/dadrion-taylor-demerson"
                                        )
                                    }
                                ],
                            },
                        },
                        {
                            "id": "active-record",
                            "status": "Active",
                            "athlete": {
                                "displayName": "Healthy Corner",
                                "position": {"abbreviation": "CB"},
                                "team": {"abbreviation": "ARI"},
                            },
                        },
                    ]
                }
            ]
        }

        injuries = normalize_espn_nfl_injuries(payload)

        self.assertEqual(len(injuries), 1)
        injury = injuries[0]
        self.assertEqual(injury["source"], "espn_nfl")
        self.assertEqual(injury["source_player_id"], "4428633")
        self.assertEqual(injury["team"], "AZ")
        self.assertEqual(injury["side"], "defense")
        self.assertEqual(injury["role"], "S")
        self.assertEqual(injury["injury_type"], "Ribs")
        self.assertEqual(injury["game_status"], "Questionable")

    def test_normalizes_weekly_and_season_espn_projections(self) -> None:
        projections, injuries = normalize_espn_players(espn_payload(), 2026, 1)

        self.assertEqual(len(projections), 3)
        self.assertEqual(
            {(row["player_name"], row["projection_period"]) for row in projections},
            {
                ("Deep Receiver", "week"),
                ("Deep Receiver", "season"),
                ("Healthy Runner", "week"),
            },
        )
        self.assertEqual(projections[0]["team"], "DET")
        self.assertEqual(len(injuries), 1)
        self.assertEqual(injuries[0]["game_status"], "QUESTIONABLE")

    def test_builds_and_verifies_append_only_snapshot(self) -> None:
        captured_at = datetime(2026, 8, 25, 18, 0, tzinfo=timezone.utc)
        spec = SnapshotSpec(
            season=2026,
            week=1,
            vintage="preseason",
            as_of=captured_at,
            captured_at=captured_at,
        )
        projections, injuries = normalize_espn_players(espn_payload(), 2026, 1)
        content = (json.dumps(espn_payload(), sort_keys=True) + "\n").encode()
        artifact = RawArtifact(
            source="espn_league",
            kind="player_pool",
            origin="fixture",
            filename="players.json",
            content=content,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            snapshot = build_snapshot(
                data_dir, spec, [artifact], projections, injuries, note="test"
            )

            self.assertEqual(verify_snapshot(snapshot), [])
            manifest = json.loads((snapshot / "manifest.json").read_text())
            self.assertEqual(manifest["counts"]["injuries"], 1)
            self.assertEqual(manifest["counts"]["projections"], 3)
            self.assertEqual(
                manifest["counts"]["projections_by_source"], {"espn_league": 3}
            )
            with (snapshot / "normalized" / "projections.csv").open() as source:
                rows = list(csv.DictReader(source))
            self.assertTrue(all(row["as_of"] == "2026-08-25T18:00:00Z" for row in rows))

            with self.assertRaisesRegex(FileExistsError, "cannot be overwritten"):
                build_snapshot(data_dir, spec, [artifact], projections, injuries)

    def test_verifier_detects_tampering(self) -> None:
        captured_at = datetime(2026, 8, 25, 18, 1, tzinfo=timezone.utc)
        spec = SnapshotSpec(2026, 1, "preseason", captured_at, captured_at)
        artifact = RawArtifact("test", "input", "fixture", "input.txt", b"before")
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot = build_snapshot(
                Path(temporary_directory), spec, [artifact], [], []
            )
            raw_path = next((snapshot / "raw").iterdir())
            raw_path.write_bytes(b"after")

            errors = verify_snapshot(snapshot)

            self.assertTrue(any("sha256 mismatch" in error for error in errors))

    def test_future_information_cutoff_is_rejected(self) -> None:
        now = datetime(2026, 8, 25, 18, 0, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "cannot be in the future"):
            parse_timestamp("2026-08-25T18:06:00Z", now)
        with self.assertRaisesRegex(ValueError, "must include a UTC offset"):
            parse_timestamp("2026-08-25T18:00:00", now)

    def test_generic_injury_probability_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "injuries.csv"
            with path.open("w", newline="") as output:
                writer = csv.DictWriter(
                    output,
                    fieldnames=[
                        "source",
                        "player_name",
                        "team",
                        "side",
                        "role",
                        "probability_playing",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "source": "test",
                        "player_name": "Safety",
                        "team": "DET",
                        "side": "defense",
                        "role": "S",
                        "probability_playing": 1.1,
                    }
                )

            with self.assertRaisesRegex(ValueError, r"must be in \[0, 1\]"):
                read_generic_injuries(path)

    def test_normalizes_fantasypros_projection_shapes_and_defender_injury(self) -> None:
        projection_payloads = [
            (
                "WR",
                {
                    "players": [
                        {
                            "fpid": 7,
                            "name": "Deep Receiver",
                            "team_id": "DET",
                            "position_id": "WR",
                            "stats": [{"points_ppr": 18.75}],
                        }
                    ]
                },
                "fixture",
            )
        ]
        injuries_payload = {
            "injuries": [
                {
                    "player_id": 8,
                    "name": "Starting Safety",
                    "team_id": "GB",
                    "position_id": "S",
                    "injury_type": "Hamstring",
                    "status": "Questionable",
                    "status_short": "Q",
                    "probability_of_playing": "0.42",
                    "practice_1": "DNP",
                    "practice_2": "Limit",
                    "practice_3": "Full",
                    "injury_update_date": "2026-09-04",
                }
            ]
        }

        projections = normalize_fantasypros_projections(projection_payloads)
        injuries = normalize_fantasypros_injuries(injuries_payload)

        self.assertEqual(projections[0]["projected_points_ppr"], 18.75)
        self.assertEqual(injuries[0]["side"], "defense")
        self.assertEqual(injuries[0]["role"], "S")
        self.assertEqual(injuries[0]["practice_status"], "Full")
        self.assertEqual(injuries[0]["probability_playing"], 0.42)

    def test_nflverse_context_uses_latest_depth_and_four_prior_games(self) -> None:
        roster = gzip.compress(
            (
                "season,team,position,status,full_name,gsis_id,espn_id,pfr_id,"
                "status_description_abbr\n"
                "2026,GB,S,ACT,Starting Safety,00-1,88,SafeSt00,A01\n"
            ).encode()
        )
        depth = gzip.compress(
            (
                "dt,team,player_name,espn_id,gsis_id,pos_abb,pos_slot,pos_rank\n"
                "2026-08-24T07:00:00Z,GB,Starting Safety,88,00-1,FS,1,2\n"
                "2026-08-25T07:00:00Z,GB,Starting Safety,88,00-1,FS,1,1\n"
            ).encode()
        )
        snap_lines = [
            "game_id,season,pfr_player_id,defense_snaps,defense_pct",
            *[
                f"2025_{week:02d}_GB_X,2025,SafeSt00,50,{share}"
                for week, share in enumerate((0.5, 0.6, 0.7, 0.8, 0.9), start=1)
            ],
        ]
        snaps = gzip.compress(("\n".join(snap_lines) + "\n").encode())

        rows = normalize_nflverse_context(roster, depth, snaps, 2026)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["role"], "S")
        self.assertEqual(rows[0]["depth_rank"], "1")
        self.assertEqual(rows[0]["depth_as_of"], "2026-08-25T07:00:00Z")
        self.assertEqual(rows[0]["prior_defense_snap_games"], 4)
        self.assertAlmostEqual(rows[0]["prior_defense_snap_share_4g"], 0.75)


if __name__ == "__main__":
    unittest.main()
