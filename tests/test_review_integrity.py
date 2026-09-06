import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import draft_board, export_espn_history, injury_snapshot
from scripts.calibrate_defender_availability import build_records, source_file
from scripts.injury_signal import verify_frozen_prediction


class ReviewIntegrityTests(unittest.TestCase):
    def test_authenticated_requests_refuse_redirects(self):
        context = SimpleNamespace(season=2026, league_id="0")
        credentials = SimpleNamespace(league_id="0", swid="test", espn_s2="test")
        calls = [
            (draft_board, lambda: draft_board.fetch_espn_players(context, credentials)),
            (draft_board, lambda: draft_board.fetch_espn_draft(context, credentials)),
            (
                export_espn_history,
                lambda: export_espn_history.request_json(
                    credentials, "https://example.test", []
                ),
            ),
            (injury_snapshot, lambda: injury_snapshot.fetch_espn_players(2026, 1, "0")),
            (
                injury_snapshot,
                lambda: injury_snapshot.fetch_fantasypros_json(
                    "nfl/injuries", {}, "test-key"
                ),
            ),
        ]
        for module, call in calls:
            with self.subTest(module=module.__name__):
                session = MagicMock()
                session.__enter__.return_value = session
                session.get.return_value.status_code = 302
                with (
                    patch.object(module, "make_session", return_value=session),
                    patch.object(injury_snapshot, "load_dotenv"),
                    patch.dict(
                        "os.environ",
                        {"ESPN_LEAGUE_ID": "0", "ESPN_SWID": "test", "ESPN_S2": "test"},
                    ),
                    self.assertRaisesRegex(RuntimeError, "redirect"),
                ):
                    call()
                self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
                session.get.return_value.json.assert_not_called()

    def test_newest_injury_report_compares_instants_across_offsets(self):
        common = {
            "game_type": "REG",
            "week": "2",
            "team": "GB",
            "gsis_id": "test",
            "position": "CB",
        }
        reports = [
            {
                **common,
                "date_modified": "2024-09-10T16:00:00-04:00",
                "report_status": "Out",
            },
            {
                **common,
                "date_modified": "2024-09-10T19:00:00Z",
                "report_status": "Questionable",
            },
        ]
        rosters = {2024: [{"team": "GB", "gsis_id": "test", "pfr_id": "test"}]}
        schedule = [
            {
                "season": "2024",
                "game_type": "REG",
                "week": "2",
                "gameday": "2024-09-15",
                "gametime": "13:00",
                "away_team": "GB",
                "home_team": "TEN",
            }
        ]
        for ordered in (reports, list(reversed(reports))):
            result = build_records([2024], {2024: ordered}, rosters, {}, schedule)
            self.assertEqual(result[0]["report_status"], "OUT")

    def test_calibration_source_rejects_paths_outside_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            source = parent / "source"
            source.mkdir()
            external = parent / "external.csv"
            external.write_text("synthetic\n")
            (source / "linked.csv").symlink_to(external)
            for path in ("../external.csv", str(external), "linked.csv"):
                manifest = {
                    "files": [
                        {
                            "kind": "injuries",
                            "season": 2024,
                            "path": path,
                            "sha256": hashlib.sha256(external.read_bytes()).hexdigest(),
                        }
                    ]
                }
                with self.subTest(path=path), self.assertRaises(ValueError):
                    source_file(source, manifest, "injuries", 2024)

    def test_frozen_prediction_rejects_external_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            prediction = parent / "prediction"
            prediction.mkdir()
            external = parent / "external.csv"
            external.write_text("synthetic\n")
            (prediction / "exposures.csv").symlink_to(external)
            manifest = {
                "schema_version": 1,
                "prediction_id": "prediction",
                "files": [
                    {
                        "path": "exposures.csv",
                        "bytes": external.stat().st_size,
                        "sha256": hashlib.sha256(external.read_bytes()).hexdigest(),
                    }
                ],
            }
            (prediction / "prediction-manifest.json").write_text(json.dumps(manifest))
            self.assertTrue(
                any(
                    "escapes snapshot" in error
                    for error in verify_frozen_prediction(prediction)
                )
            )
