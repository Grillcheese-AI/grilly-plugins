"""
Merit ledger for elephant-coder — gamified reward system for Claude.

Tracks merit points earned by successfully completing tasks, receiving
positive user feedback, and demonstrating good engineering practices.
Stored globally so merits persist across projects and sessions.

Points are awarded for:
- Task completion (+10)
- Positive user feedback (+5)
- Proactive helpful action (+3)
- Bug caught before shipping (+8)
- Test written (+2)
- Clean code review (+4)
- Module created (+6)
- User objective advanced (+7)

Points can be deducted for:
- Task failed/reverted (-5)
- User expressed frustration from Claude's action (-3)
- Scope creep (-2)

The ledger syncs to merit_ledger.json for portability and to the
global SQLite database for fast querying.
"""

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("elephant-coder.merits")

# Merit point values for different actions
MERIT_VALUES = {
    "task_completed": 10,
    "positive_feedback": 5,
    "proactive_action": 3,
    "bug_caught": 8,
    "test_written": 2,
    "clean_review": 4,
    "module_created": 6,
    "objective_advanced": 7,
    "excellent_work": 15,
    "task_failed": -5,
    "user_frustrated": -3,
    "scope_creep": -2,
    "custom": 0,
}

# Rank thresholds
RANKS = [
    (0, "Novice"),
    (25, "Apprentice"),
    (75, "Journeyman"),
    (150, "Adept"),
    (300, "Expert"),
    (500, "Master"),
    (800, "Grandmaster"),
    (1200, "Legend"),
    (2000, "Transcendent"),
]


@dataclass
class MeritEntry:
    """A single merit event."""
    timestamp: float
    reason: str
    category: str
    points: int
    project: str
    cumulative: int


def _db_path() -> Path:
    """Global merit database."""
    base = Path.home() / ".elephant-coder"
    base.mkdir(parents=True, exist_ok=True)
    return base / "merit_ledger.db"


def _get_rank(total: int) -> str:
    """Get rank title for a point total."""
    rank = RANKS[0][1]
    for threshold, title in RANKS:
        if total >= threshold:
            rank = title
    return rank


def _next_rank(total: int) -> tuple[str, int]:
    """Get next rank and points needed."""
    for i, (threshold, title) in enumerate(RANKS):
        if total < threshold:
            return title, threshold - total
    return RANKS[-1][1], 0


class MeritLedger:
    """Global merit tracking system.

    Stores merit events in SQLite and syncs to a JSON file for portability.
    """

    def __init__(self, json_path: str | None = None):
        self._db = _db_path()
        self._json_path = json_path
        self._conn = sqlite3.connect(str(self._db))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

        # Import from JSON if it has data we don't
        if json_path:
            self._sync_from_json(json_path)

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS merit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                reason TEXT NOT NULL,
                category TEXT NOT NULL,
                points INTEGER NOT NULL,
                project TEXT DEFAULT '',
                cumulative INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS merit_summary (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_merit_timestamp
                ON merit_log(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_merit_category
                ON merit_log(category);
        """)
        # Initialize total if not exists
        row = self._conn.execute(
            "SELECT value FROM merit_summary WHERE key = 'total_points'"
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO merit_summary (key, value) VALUES ('total_points', '0')"
            )
            self._conn.commit()

    def award(self, category: str, reason: str,
              points: int | None = None, project: str = "") -> MeritEntry:
        """Award merit points.

        Args:
            category: Type of merit (see MERIT_VALUES keys)
            reason: Why points were awarded
            points: Override default points for category (optional)
            project: Which project this was for
        """
        if points is None:
            if category == "custom":
                points = 1
            else:
                points = MERIT_VALUES.get(category, 1)

        now = time.time()
        total = self._get_total() + points

        self._conn.execute(
            """INSERT INTO merit_log (timestamp, reason, category, points, project, cumulative)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now, reason, category, points, project, total)
        )
        self._conn.execute(
            "UPDATE merit_summary SET value = ? WHERE key = 'total_points'",
            (str(total),)
        )
        self._conn.commit()

        entry = MeritEntry(
            timestamp=now, reason=reason, category=category,
            points=points, project=project, cumulative=total,
        )

        # Sync to JSON
        self._sync_to_json()

        logger.info("Merit awarded: %+d (%s) — total: %d", points, category, total)
        return entry

    def deduct(self, category: str, reason: str,
               points: int | None = None, project: str = "") -> MeritEntry:
        """Deduct merit points. Points value should be positive (will be negated)."""
        if points is None:
            pts = MERIT_VALUES.get(category, -1)
            if pts > 0:
                pts = -pts
        else:
            pts = -abs(points)
        return self.award(category, reason, points=pts, project=project)

    def get_total(self) -> int:
        return self._get_total()

    def get_rank(self) -> dict:
        """Get current rank info."""
        total = self._get_total()
        rank = _get_rank(total)
        next_title, points_needed = _next_rank(total)
        return {
            "total_points": total,
            "rank": rank,
            "next_rank": next_title,
            "points_to_next": points_needed,
        }

    def get_log(self, limit: int = 20, category: str | None = None) -> list[MeritEntry]:
        """Get recent merit events."""
        if category:
            rows = self._conn.execute(
                "SELECT * FROM merit_log WHERE category = ? ORDER BY timestamp DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM merit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [MeritEntry(
            timestamp=r["timestamp"], reason=r["reason"],
            category=r["category"], points=r["points"],
            project=r["project"], cumulative=r["cumulative"],
        ) for r in rows]

    def get_stats(self) -> dict:
        """Detailed merit statistics."""
        total = self._get_total()
        rank_info = self.get_rank()

        # By category
        by_category = {}
        for r in self._conn.execute(
            "SELECT category, SUM(points) AS pts, COUNT(*) AS cnt "
            "FROM merit_log GROUP BY category ORDER BY pts DESC"
        ).fetchall():
            by_category[r["category"]] = {"points": r["pts"], "count": r["cnt"]}

        # By project
        by_project = {}
        for r in self._conn.execute(
            "SELECT project, SUM(points) AS pts, COUNT(*) AS cnt "
            "FROM merit_log WHERE project != '' GROUP BY project ORDER BY pts DESC"
        ).fetchall():
            by_project[r["project"]] = {"points": r["pts"], "count": r["cnt"]}

        # Streaks
        recent = self._conn.execute(
            "SELECT points FROM merit_log ORDER BY timestamp DESC LIMIT 20"
        ).fetchall()
        streak = 0
        for r in recent:
            if r["points"] > 0:
                streak += 1
            else:
                break

        # Total events
        event_count = self._conn.execute(
            "SELECT COUNT(*) AS c FROM merit_log"
        ).fetchone()["c"]

        return {
            **rank_info,
            "total_events": event_count,
            "positive_streak": streak,
            "by_category": by_category,
            "by_project": by_project,
        }

    def _get_total(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM merit_summary WHERE key = 'total_points'"
        ).fetchone()
        return int(row["value"]) if row else 0

    def _sync_to_json(self) -> None:
        """Write current state to JSON file."""
        if not self._json_path:
            return
        try:
            total = self._get_total()
            recent = self.get_log(limit=50)
            data = {
                "total_merit_points": total,
                "rank": _get_rank(total),
                "log": [
                    {
                        "timestamp": e.timestamp,
                        "reason": e.reason,
                        "category": e.category,
                        "points": e.points,
                        "project": e.project,
                        "cumulative": e.cumulative,
                    }
                    for e in recent
                ]
            }
            Path(self._json_path).write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning("Failed to sync merit JSON: %s", exc)

    def _sync_from_json(self, json_path: str) -> None:
        """Import merit events from JSON that aren't in the DB yet."""
        try:
            path = Path(json_path)
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data.get("log", [])
            if not entries:
                return

            # Check if DB is empty
            db_count = self._conn.execute(
                "SELECT COUNT(*) AS c FROM merit_log"
            ).fetchone()["c"]
            if db_count > 0:
                return  # DB already has data, don't double-import

            for entry in entries:
                self._conn.execute(
                    """INSERT INTO merit_log
                       (timestamp, reason, category, points, project, cumulative)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (entry.get("timestamp", 0), entry.get("reason", ""),
                     entry.get("category", "custom"), entry.get("points", 0),
                     entry.get("project", ""), entry.get("cumulative", 0))
                )
            total = data.get("total_merit_points", 0)
            self._conn.execute(
                "UPDATE merit_summary SET value = ? WHERE key = 'total_points'",
                (str(total),)
            )
            self._conn.commit()
            logger.info("Imported %d merit entries from JSON", len(entries))
        except Exception as exc:
            logger.warning("Failed to import merit JSON: %s", exc)

    def close(self) -> None:
        self._sync_to_json()
        self._conn.close()
