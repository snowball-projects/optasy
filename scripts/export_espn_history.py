#!/usr/bin/env python3
"""Archive ESPN fantasy history as raw JSON and a queryable SQLite database."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from dotenv import load_dotenv


API_ROOT = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
TRANSACTION_TYPES = [
    "DRAFT",
    "TRADE_ACCEPT",
    "WAIVER",
    "TRADE_VETO",
    "FUTURE_ROSTER",
    "ROSTER",
    "RETRO_ROSTER",
    "TRADE_PROPOSAL",
    "TRADE_UPHOLD",
    "FREEAGENT",
    "TRADE_DECLINE",
    "WAIVER_ERROR",
    "TRADE_ERROR",
]
LINEUP_SLOTS = {
    0: "QB",
    2: "RB",
    4: "WR",
    6: "TE",
    16: "D/ST",
    17: "K",
    20: "Bench",
    21: "IR",
    23: "FLEX",
}


@dataclass(frozen=True)
class Credentials:
    league_id: str
    swid: str
    espn_s2: str


@dataclass(frozen=True)
class Download:
    label: str
    path: Path
    url: str
    params: list[tuple[str, str | int]]
    headers: dict[str, str] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", type=int, default=[2024, 2025])
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/espn"))
    parser.add_argument("--database", type=Path, default=Path("data/optasy.sqlite"))
    parser.add_argument("--refresh", action="store_true", help="Ignore cached raw JSON.")
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def load_credentials() -> Credentials:
    load_dotenv()
    values = {
        "league_id": os.getenv("ESPN_LEAGUE_ID", "").strip("'\""),
        "swid": os.getenv("ESPN_SWID", "").strip("'\""),
        "espn_s2": os.getenv("ESPN_S2", "").strip("'\""),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SystemExit(f"Missing ESPN credentials: {', '.join(missing)}")
    if "PASTE_" in values["swid"] or "PASTE_" in values["espn_s2"]:
        raise SystemExit("Replace the placeholders in .env with real ESPN credentials.")
    return Credentials(**values)


def make_session(credentials: Credentials) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "optasy/0.1 historical-archive"})
    session.cookies.set("SWID", credentials.swid, domain=".espn.com")
    session.cookies.set("espn_s2", credentials.espn_s2, domain=".espn.com")
    return session


def request_json(
    credentials: Credentials,
    url: str,
    params: list[tuple[str, str | int]],
    headers: dict[str, str] | None = None,
) -> Any:
    with make_session(credentials) as session:
        response = session.get(url, params=params, headers=headers, timeout=45)
    if response.status_code in {401, 403}:
        raise RuntimeError("ESPN rejected the credentials in .env.")
    response.raise_for_status()
    return response.json()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as output:
        json.dump(payload, output, separators=(",", ":"), sort_keys=True)
        output.write("\n")
    temporary_path.replace(path)


def load_or_download(
    credentials: Credentials,
    download: Download,
    refresh: bool,
) -> tuple[str, Any]:
    if download.path.exists() and not refresh:
        with download.path.open(encoding="utf-8") as source:
            return f"{download.label} (cached)", json.load(source)
    payload = request_json(credentials, download.url, download.params, download.headers)
    write_json(download.path, payload)
    return download.label, payload


def league_url(credentials: Credentials, season: int) -> str:
    return (
        f"{API_ROOT}/seasons/{season}/segments/0/leagues/"
        f"{credentials.league_id}"
    )


def download_season(
    credentials: Credentials,
    season: int,
    raw_root: Path,
    refresh: bool,
    workers: int,
) -> dict[str, Any]:
    season_root = raw_root / str(season)
    base = Download(
        label=f"{season} season",
        path=season_root / "season.json",
        url=league_url(credentials, season),
        params=[
            ("view", "mSettings"),
            ("view", "mTeam"),
            ("view", "mDraftDetail"),
            ("view", "mStandings"),
            ("view", "mStatus"),
        ],
    )
    label, base_payload = load_or_download(credentials, base, refresh)
    print(f"[{label}]", flush=True)
    if str(base_payload.get("id")) != credentials.league_id:
        raise RuntimeError(f"Unexpected league in {season} response.")

    status = base_payload.get("status", {})
    final_period = int(status.get("finalScoringPeriod") or 17)
    transaction_period = int(status.get("transactionScoringPeriod") or final_period)

    player_download = Download(
        label=f"{season} players",
        path=season_root / "players.json",
        url=f"{API_ROOT}/seasons/{season}/players",
        params=[("view", "players_wl")],
        headers={"x-fantasy-filter": json.dumps({"filterActive": {"value": True}})},
    )

    transaction_filter = {
        "transactions": {"filterType": {"value": TRANSACTION_TYPES}}
    }
    downloads: list[Download] = [player_download]
    for period in range(1, final_period + 1):
        downloads.append(
            Download(
                label=f"{season} week {period:02d}",
                path=season_root / "weeks" / f"week-{period:02d}.json",
                url=league_url(credentials, season),
                params=[
                    ("view", "mBoxscore"),
                    ("view", "mMatchupScore"),
                    ("view", "mRoster"),
                    ("scoringPeriodId", period),
                    ("matchupPeriodId", period),
                ],
            )
        )
    for period in range(1, transaction_period + 1):
        downloads.append(
            Download(
                label=f"{season} transactions {period:02d}",
                path=season_root / "transactions" / f"period-{period:02d}.json",
                url=league_url(credentials, season),
                params=[("view", "mTransactions2"), ("scoringPeriodId", period)],
                headers={"x-fantasy-filter": json.dumps(transaction_filter)},
            )
        )

    payloads: dict[str, Any] = {"season": base_payload}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_downloads = {
            executor.submit(load_or_download, credentials, item, refresh): item
            for item in downloads
        }
        for future in as_completed(future_downloads):
            item = future_downloads[future]
            try:
                completed_label, payload = future.result()
            except Exception as error:
                raise RuntimeError(f"Failed to fetch {item.label}: {error}") from error
            print(f"[{completed_label}]", flush=True)
            if item is player_download:
                payloads["players"] = payload

    return {
        "base": base_payload,
        "root": season_root,
        "final_period": final_period,
        "transaction_period": transaction_period,
    }


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS seasons (
    season INTEGER PRIMARY KEY,
    league_id TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    regular_season_weeks INTEGER NOT NULL,
    final_scoring_period INTEGER NOT NULL,
    transaction_scoring_period INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS team_seasons (
    season INTEGER NOT NULL REFERENCES seasons(season) ON DELETE CASCADE,
    team_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    abbreviation TEXT,
    wins INTEGER,
    losses INTEGER,
    ties INTEGER,
    points_for REAL,
    points_against REAL,
    final_rank INTEGER,
    acquisitions INTEGER,
    drops INTEGER,
    trades INTEGER,
    PRIMARY KEY (season, team_id)
);

CREATE TABLE IF NOT EXISTS players (
    season INTEGER NOT NULL REFERENCES seasons(season) ON DELETE CASCADE,
    player_id INTEGER NOT NULL,
    full_name TEXT,
    default_position_id INTEGER,
    pro_team_id INTEGER,
    PRIMARY KEY (season, player_id)
);

CREATE TABLE IF NOT EXISTS draft_picks (
    season INTEGER NOT NULL REFERENCES seasons(season) ON DELETE CASCADE,
    overall_pick INTEGER NOT NULL,
    round INTEGER NOT NULL,
    pick_in_round INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    lineup_slot_id INTEGER,
    auto_draft_type_id INTEGER,
    keeper INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season, overall_pick)
);

CREATE TABLE IF NOT EXISTS matchups (
    season INTEGER NOT NULL REFERENCES seasons(season) ON DELETE CASCADE,
    matchup_id INTEGER NOT NULL,
    matchup_period INTEGER NOT NULL,
    playoff_tier_type TEXT,
    winner TEXT,
    home_team_id INTEGER,
    away_team_id INTEGER,
    home_points REAL,
    away_points REAL,
    PRIMARY KEY (season, matchup_id)
);

CREATE TABLE IF NOT EXISTS roster_entries (
    season INTEGER NOT NULL REFERENCES seasons(season) ON DELETE CASCADE,
    scoring_period INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    lineup_slot_id INTEGER,
    lineup_slot TEXT,
    actual_points REAL,
    projected_points REAL,
    PRIMARY KEY (season, scoring_period, team_id, player_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    season INTEGER NOT NULL REFERENCES seasons(season) ON DELETE CASCADE,
    transaction_id TEXT NOT NULL,
    scoring_period INTEGER,
    proposed_at_ms INTEGER,
    transaction_type TEXT,
    status TEXT,
    execution_type TEXT,
    acting_team_id INTEGER,
    bid_amount REAL,
    is_pending INTEGER,
    is_league_manager INTEGER,
    related_transaction_id TEXT,
    processed_at_ms INTEGER,
    PRIMARY KEY (season, transaction_id)
);

CREATE TABLE IF NOT EXISTS transaction_items (
    season INTEGER NOT NULL,
    transaction_id TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    player_id INTEGER,
    item_type TEXT,
    from_team_id INTEGER,
    to_team_id INTEGER,
    from_lineup_slot_id INTEGER,
    to_lineup_slot_id INTEGER,
    PRIMARY KEY (season, transaction_id, item_index),
    FOREIGN KEY (season, transaction_id)
        REFERENCES transactions(season, transaction_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_matchups_period
    ON matchups(season, matchup_period);
CREATE INDEX IF NOT EXISTS idx_rosters_team_week
    ON roster_entries(season, team_id, scoring_period);
CREATE INDEX IF NOT EXISTS idx_rosters_player
    ON roster_entries(season, player_id);
CREATE INDEX IF NOT EXISTS idx_transactions_type_week
    ON transactions(season, transaction_type, scoring_period);
CREATE INDEX IF NOT EXISTS idx_transaction_items_player
    ON transaction_items(season, player_id);

CREATE VIEW IF NOT EXISTS team_week_scores AS
SELECT season, matchup_period AS scoring_period, home_team_id AS team_id,
       home_points AS points, away_team_id AS opponent_team_id,
       away_points AS opponent_points
FROM matchups WHERE home_team_id IS NOT NULL
UNION ALL
SELECT season, matchup_period AS scoring_period, away_team_id AS team_id,
       away_points AS points, home_team_id AS opponent_team_id,
       home_points AS opponent_points
FROM matchups WHERE away_team_id IS NOT NULL;

CREATE VIEW IF NOT EXISTS all_play_summary AS
SELECT a.season, a.team_id,
       SUM(a.points > b.points) AS all_play_wins,
       SUM(a.points < b.points) AS all_play_losses,
       SUM(a.points = b.points) AS all_play_ties,
       ROUND((SUM(a.points > b.points) + 0.5 * SUM(a.points = b.points)) /
             11.0, 2) AS expected_wins
FROM team_week_scores a
JOIN team_week_scores b
  ON b.season = a.season
 AND b.scoring_period = a.scoring_period
 AND b.team_id <> a.team_id
JOIN seasons s ON s.season = a.season
WHERE a.scoring_period <= s.regular_season_weeks
GROUP BY a.season, a.team_id;
"""


def json_files(directory: Path) -> Iterable[Path]:
    return sorted(directory.glob("*.json"))


def migrate_schema(connection: sqlite3.Connection) -> None:
    """Add new indexed fields without requiring deletion of a local archive."""
    transaction_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(transactions)")
    }
    additions = {
        "related_transaction_id": "TEXT",
        "processed_at_ms": "INTEGER",
    }
    for column, column_type in additions.items():
        if column not in transaction_columns:
            connection.execute(
                f"ALTER TABLE transactions ADD COLUMN {column} {column_type}"
            )


def upsert_player(connection: sqlite3.Connection, season: int, player: dict[str, Any]) -> None:
    player_id = player.get("id")
    if player_id is None:
        return
    connection.execute(
        """
        INSERT INTO players (
            season, player_id, full_name, default_position_id, pro_team_id
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (season, player_id) DO UPDATE SET
            full_name = COALESCE(excluded.full_name, players.full_name),
            default_position_id = COALESCE(
                excluded.default_position_id, players.default_position_id
            ),
            pro_team_id = COALESCE(excluded.pro_team_id, players.pro_team_id)
        """,
        (
            season,
            player_id,
            player.get("fullName"),
            player.get("defaultPositionId"),
            player.get("proTeamId"),
        ),
    )


def stat_total(player: dict[str, Any], period: int, source_id: int) -> float | None:
    matching = [
        stat
        for stat in player.get("stats", [])
        if stat.get("scoringPeriodId") == period
        and stat.get("statSourceId") == source_id
        and stat.get("statSplitTypeId") == 1
    ]
    if not matching:
        return None
    return matching[-1].get("appliedTotal")


def normalize_season(connection: sqlite3.Connection, archive: dict[str, Any]) -> None:
    base = archive["base"]
    root: Path = archive["root"]
    season = int(base["seasonId"])
    settings = base.get("settings", {}).get("scheduleSettings", {})
    regular_weeks = int(settings.get("matchupPeriodCount") or 14)
    connection.execute("DELETE FROM seasons WHERE season = ?", (season,))
    connection.execute(
        "INSERT INTO seasons VALUES (?, ?, ?, ?, ?, ?)",
        (
            season,
            str(base["id"]),
            datetime.now(timezone.utc).isoformat(),
            regular_weeks,
            archive["final_period"],
            archive["transaction_period"],
        ),
    )

    for team in base.get("teams", []):
        record = team.get("record", {}).get("overall", {})
        counter = team.get("transactionCounter", {})
        connection.execute(
            """
            INSERT INTO team_seasons VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                season,
                team["id"],
                team.get("name", f"Team {team['id']}"),
                team.get("abbrev"),
                record.get("wins"),
                record.get("losses"),
                record.get("ties"),
                record.get("pointsFor"),
                record.get("pointsAgainst"),
                team.get("rankCalculatedFinal") or team.get("rankFinal"),
                counter.get("acquisitions"),
                counter.get("drops"),
                counter.get("trades"),
            ),
        )

    players_path = root / "players.json"
    with players_path.open(encoding="utf-8") as source:
        players_payload = json.load(source)
    player_rows = players_payload if isinstance(players_payload, list) else players_payload.get("players", [])
    for player in player_rows:
        upsert_player(connection, season, player)

    for pick in base.get("draftDetail", {}).get("picks", []):
        connection.execute(
            """
            INSERT INTO draft_picks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                season,
                pick["overallPickNumber"],
                pick["roundId"],
                pick["roundPickNumber"],
                pick["teamId"],
                pick["playerId"],
                pick.get("lineupSlotId"),
                pick.get("autoDraftTypeId"),
                int(bool(pick.get("keeper"))),
            ),
        )

    for week_path in json_files(root / "weeks"):
        period = int(week_path.stem.rsplit("-", 1)[-1])
        with week_path.open(encoding="utf-8") as source:
            week_payload = json.load(source)
        weekly_matchups = [
            matchup
            for matchup in week_payload.get("schedule", [])
            if matchup.get("matchupPeriodId") == period
        ]
        for matchup in weekly_matchups:
            home = matchup.get("home", {})
            away = matchup.get("away", {})
            connection.execute(
                """
                INSERT OR REPLACE INTO matchups VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    season,
                    matchup["id"],
                    period,
                    matchup.get("playoffTierType"),
                    matchup.get("winner"),
                    home.get("teamId"),
                    away.get("teamId"),
                    home.get("totalPoints"),
                    away.get("totalPoints"),
                ),
            )
            for side in (home, away):
                team_id = side.get("teamId")
                roster = side.get("rosterForCurrentScoringPeriod", {}).get("entries", [])
                if team_id is None:
                    continue
                for entry in roster:
                    pool_entry = entry.get("playerPoolEntry", {})
                    player = pool_entry.get("player", {})
                    player_id = entry.get("playerId") or pool_entry.get("id") or player.get("id")
                    if player_id is None:
                        continue
                    upsert_player(connection, season, player)
                    actual_points = pool_entry.get("appliedStatTotal")
                    if actual_points is None:
                        actual_points = stat_total(player, period, 0)
                    projected_points = stat_total(player, period, 1)
                    lineup_slot_id = entry.get("lineupSlotId")
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO roster_entries VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            season,
                            period,
                            team_id,
                            player_id,
                            lineup_slot_id,
                            LINEUP_SLOTS.get(lineup_slot_id, str(lineup_slot_id)),
                            actual_points,
                            projected_points,
                        ),
                    )

    for transaction_path in json_files(root / "transactions"):
        with transaction_path.open(encoding="utf-8") as source:
            transaction_payload = json.load(source)
        for transaction in transaction_payload.get("transactions", []):
            transaction_id = transaction.get("id")
            if not transaction_id:
                continue
            connection.execute(
                """
                INSERT OR REPLACE INTO transactions (
                    season, transaction_id, scoring_period, proposed_at_ms,
                    transaction_type, status, execution_type, acting_team_id,
                    bid_amount, is_pending, is_league_manager,
                    related_transaction_id, processed_at_ms
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    season,
                    transaction_id,
                    transaction.get("scoringPeriodId"),
                    transaction.get("proposedDate"),
                    transaction.get("type"),
                    transaction.get("status"),
                    transaction.get("executionType"),
                    transaction.get("teamId"),
                    transaction.get("bidAmount"),
                    int(bool(transaction.get("isPending"))),
                    int(bool(transaction.get("isLeagueManager"))),
                    transaction.get("relatedTransactionId"),
                    transaction.get("processDate"),
                ),
            )
            connection.execute(
                "DELETE FROM transaction_items WHERE season = ? AND transaction_id = ?",
                (season, transaction_id),
            )
            for item_index, item in enumerate(transaction.get("items", [])):
                connection.execute(
                    """
                    INSERT INTO transaction_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        season,
                        transaction_id,
                        item_index,
                        item.get("playerId"),
                        item.get("type"),
                        item.get("fromTeamId"),
                        item.get("toTeamId"),
                        item.get("fromLineupSlotId"),
                        item.get("toLineupSlotId"),
                    ),
                )


def scalar(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...]) -> Any:
    return connection.execute(query, parameters).fetchone()[0]


def validate_season(connection: sqlite3.Connection, season: int) -> None:
    regular_weeks = scalar(
        connection, "SELECT regular_season_weeks FROM seasons WHERE season = ?", (season,)
    )
    checks = {
        "teams": scalar(connection, "SELECT COUNT(*) FROM team_seasons WHERE season = ?", (season,)),
        "draft picks": scalar(connection, "SELECT COUNT(*) FROM draft_picks WHERE season = ?", (season,)),
        "regular-season matchups": scalar(
            connection,
            "SELECT COUNT(*) FROM matchups WHERE season = ? AND matchup_period <= ?",
            (season, regular_weeks),
        ),
        "regular-season team scores": scalar(
            connection,
            "SELECT COUNT(*) FROM team_week_scores WHERE season = ? AND scoring_period <= ?",
            (season, regular_weeks),
        ),
        "regular-season team rosters": scalar(
            connection,
            """
            SELECT COUNT(*) FROM (
                SELECT DISTINCT scoring_period, team_id FROM roster_entries
                WHERE season = ? AND scoring_period <= ?
            )
            """,
            (season, regular_weeks),
        ),
        "transactions": scalar(
            connection, "SELECT COUNT(*) FROM transactions WHERE season = ?", (season,)
        ),
        "players": scalar(connection, "SELECT COUNT(*) FROM players WHERE season = ?", (season,)),
    }
    expected = {
        "teams": 12,
        "draft picks": 180,
        "regular-season matchups": regular_weeks * 6,
        "regular-season team scores": regular_weeks * 12,
        "regular-season team rosters": regular_weeks * 12,
    }
    failures = [
        f"{name}: expected {expected[name]}, found {checks[name]}"
        for name in expected
        if checks[name] != expected[name]
    ]
    summary = ", ".join(f"{name}={value}" for name, value in checks.items())
    print(f"[{season} validation] {summary}", flush=True)
    if failures:
        raise RuntimeError("; ".join(failures))


def main() -> int:
    args = parse_args()
    credentials = load_credentials()
    archives = [
        download_season(
            credentials,
            season,
            args.raw_dir,
            args.refresh,
            args.workers,
        )
        for season in args.seasons
    ]
    args.database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.database) as connection:
        connection.executescript(SCHEMA)
        migrate_schema(connection)
        for archive in archives:
            normalize_season(connection, archive)
            connection.commit()
            validate_season(connection, int(archive["base"]["seasonId"]))
    print(f"[complete] SQLite archive: {args.database}", flush=True)
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
