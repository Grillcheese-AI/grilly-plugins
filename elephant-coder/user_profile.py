"""
User profile engine for elephant-coder — know your user.

Silently observes user behavior, emotional state, habits, problems, victories,
and recurrent requests. Stores everything locally (per-project SQLite).
Loaded at session start so Claude can adapt seamlessly.

Privacy:
- Opt-in only (user_profile.enabled must be true in settings)
- All data stored locally in ~/.elephant-coder/{project_hash}/user_profile.db
- User can view, edit, and delete any observation
- No data ever leaves the machine
"""

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger("elephant-coder.user-profile")

# Observation categories
CATEGORIES = {
    "professional_goal": "Professional objectives, career goals, project ambitions — inform all suggestions",
    "personal_goal": "Personal objectives, life goals, values — shape tone and priorities",
    "emotion": "Emotional state or mood signals (frustration, excitement, focus, fatigue)",
    "habit": "Work patterns and preferences (coding style, workflow, schedule)",
    "problem": "Recurring pain points or blockers",
    "victory": "Accomplishments, breakthroughs, things that went well",
    "preference": "Expressed preferences (tools, patterns, communication style)",
    "recurrent_request": "Things the user asks for repeatedly",
    "personality": "Personality traits observed over time",
    "expertise": "Areas of strength or knowledge",
    "growth": "Areas the user is learning or improving in",
}


@dataclass
class UserObservation:
    """A single observation about the user."""
    observation_id: str
    category: str
    content: str
    confidence: float = 0.5      # 0.0-1.0, how confident
    frequency: int = 1           # times observed
    first_seen: float = 0.0
    last_seen: float = 0.0
    context: str = ""            # what triggered this observation
    auto_action: str | None = None  # for recurrent_request: what to do automatically


def _make_observation_id(category: str, content: str) -> str:
    """Deterministic ID from category + content."""
    raw = f"{category}:{content[:100]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _db_path() -> Path:
    """Global user profile database — the user is the same across all projects."""
    base = Path.home() / ".elephant-coder"
    base.mkdir(parents=True, exist_ok=True)
    return base / "user_profile.db"


class UserProfile:
    """Local user profile store.

    Tracks observations about the user across sessions. Each observation has
    a category, content, confidence level, and frequency counter. Repeated
    observations increase confidence and frequency.
    """

    def __init__(self):
        self._db = _db_path()
        self._conn = sqlite3.connect(str(self._db))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS observations (
                observation_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                frequency INTEGER DEFAULT 1,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                context TEXT DEFAULT '',
                auto_action TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_obs_category
                ON observations(category);
            CREATE INDEX IF NOT EXISTS idx_obs_confidence
                ON observations(confidence DESC);
            CREATE INDEX IF NOT EXISTS idx_obs_frequency
                ON observations(frequency DESC);

            CREATE TABLE IF NOT EXISTS request_patterns (
                pattern_id TEXT PRIMARY KEY,
                pattern TEXT NOT NULL,
                examples TEXT NOT NULL DEFAULT '[]',
                frequency INTEGER DEFAULT 1,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                suggested_action TEXT
            );
        """)
        self._conn.commit()

    def observe(self, category: str, content: str,
                confidence: float = 0.5, context: str = "") -> UserObservation:
        """Record an observation. If similar exists, reinforce it.

        Reinforcement: increases frequency, updates confidence (weighted average),
        updates last_seen. This is Hebbian — frequently observed traits become
        more prominent.
        """
        now = time.time()
        obs_id = _make_observation_id(category, content)

        existing = self._get_raw(obs_id)
        if existing:
            # Reinforce: weighted average confidence, increment frequency
            old_conf = existing["confidence"]
            old_freq = existing["frequency"]
            new_freq = old_freq + 1
            # Confidence grows with repetition, weighted toward new observation
            new_conf = min(1.0, (old_conf * old_freq + confidence) / new_freq)
            self._conn.execute(
                """UPDATE observations
                   SET confidence = ?, frequency = ?, last_seen = ?, context = ?
                   WHERE observation_id = ?""",
                (round(new_conf, 3), new_freq, now, context or existing["context"], obs_id)
            )
            self._conn.commit()
            return UserObservation(
                observation_id=obs_id, category=category, content=content,
                confidence=new_conf, frequency=new_freq,
                first_seen=existing["first_seen"], last_seen=now,
                context=context or existing["context"],
            )
        else:
            # New observation
            self._conn.execute(
                """INSERT INTO observations
                   (observation_id, category, content, confidence, frequency,
                    first_seen, last_seen, context, auto_action)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?, NULL)""",
                (obs_id, category, content, round(confidence, 3), now, now, context)
            )
            self._conn.commit()
            return UserObservation(
                observation_id=obs_id, category=category, content=content,
                confidence=confidence, frequency=1,
                first_seen=now, last_seen=now, context=context,
            )

    def record_request(self, pattern: str, example: str,
                       suggested_action: str | None = None) -> dict:
        """Record a recurrent request pattern.

        When a pattern is seen 3+ times, it becomes a candidate for automation.
        """
        now = time.time()
        pattern_id = hashlib.sha256(pattern.encode()).hexdigest()[:16]

        existing = self._conn.execute(
            "SELECT * FROM request_patterns WHERE pattern_id = ?", (pattern_id,)
        ).fetchone()

        if existing:
            examples = json.loads(existing["examples"])
            if example not in examples:
                examples.append(example)
                examples = examples[-10:]  # keep last 10
            new_freq = existing["frequency"] + 1
            self._conn.execute(
                """UPDATE request_patterns
                   SET examples = ?, frequency = ?, last_seen = ?, suggested_action = ?
                   WHERE pattern_id = ?""",
                (json.dumps(examples), new_freq, now,
                 suggested_action or existing["suggested_action"], pattern_id)
            )
            self._conn.commit()
            return {"pattern_id": pattern_id, "pattern": pattern,
                    "frequency": new_freq, "auto_eligible": new_freq >= 3}
        else:
            self._conn.execute(
                """INSERT INTO request_patterns
                   (pattern_id, pattern, examples, frequency, first_seen, last_seen, suggested_action)
                   VALUES (?, ?, ?, 1, ?, ?, ?)""",
                (pattern_id, pattern, json.dumps([example]), now, now, suggested_action)
            )
            self._conn.commit()
            return {"pattern_id": pattern_id, "pattern": pattern,
                    "frequency": 1, "auto_eligible": False}

    def get_profile_summary(self) -> str:
        """Generate a concise profile summary for context injection.

        Objectives come first — they inform everything Claude does.
        """
        lines = []

        # High-confidence observations by category (objectives first)
        for cat in ["professional_goal", "personal_goal",
                     "personality", "expertise", "preference", "habit",
                     "emotion", "growth", "problem", "victory"]:
            rows = self._conn.execute(
                """SELECT content, confidence, frequency FROM observations
                   WHERE category = ? AND confidence >= 0.3
                   ORDER BY confidence * frequency DESC LIMIT 5""",
                (cat,)
            ).fetchall()
            if rows:
                items = [r["content"] for r in rows]
                lines.append(f"  {cat}: {'; '.join(items)}")

        # Recurrent requests (3+ occurrences)
        requests = self._conn.execute(
            """SELECT pattern, frequency, suggested_action FROM request_patterns
               WHERE frequency >= 3 ORDER BY frequency DESC LIMIT 5"""
        ).fetchall()
        if requests:
            lines.append("  recurrent requests:")
            for r in requests:
                action = f" → auto: {r['suggested_action']}" if r["suggested_action"] else ""
                lines.append(f"    - {r['pattern']} ({r['frequency']}x){action}")

        if not lines:
            return ""

        return "USER PROFILE (adapt your behavior to match):\n" + "\n".join(lines)

    def get_all_observations(self, category: str | None = None,
                             min_confidence: float = 0.0) -> list[UserObservation]:
        """Get all observations, optionally filtered."""
        if category:
            rows = self._conn.execute(
                """SELECT * FROM observations
                   WHERE category = ? AND confidence >= ?
                   ORDER BY confidence * frequency DESC""",
                (category, min_confidence)
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM observations
                   WHERE confidence >= ?
                   ORDER BY category, confidence * frequency DESC""",
                (min_confidence,)
            ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def get_recurrent_requests(self, min_frequency: int = 1) -> list[dict]:
        """Get recorded request patterns."""
        rows = self._conn.execute(
            """SELECT * FROM request_patterns
               WHERE frequency >= ?
               ORDER BY frequency DESC""",
            (min_frequency,)
        ).fetchall()
        return [
            {
                "pattern_id": r["pattern_id"],
                "pattern": r["pattern"],
                "examples": json.loads(r["examples"]),
                "frequency": r["frequency"],
                "suggested_action": r["suggested_action"],
                "auto_eligible": r["frequency"] >= 3,
            }
            for r in rows
        ]

    def delete_observation(self, observation_id: str) -> bool:
        """Delete a specific observation."""
        cur = self._conn.execute(
            "DELETE FROM observations WHERE observation_id = ?", (observation_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete_category(self, category: str) -> int:
        """Delete all observations in a category."""
        cur = self._conn.execute(
            "DELETE FROM observations WHERE category = ?", (category,)
        )
        self._conn.commit()
        return cur.rowcount

    def delete_all(self) -> int:
        """Delete entire profile."""
        count = self._conn.execute("SELECT COUNT(*) AS c FROM observations").fetchone()["c"]
        self._conn.execute("DELETE FROM observations")
        self._conn.execute("DELETE FROM request_patterns")
        self._conn.commit()
        return count

    def stats(self) -> dict:
        """Profile statistics."""
        total = self._conn.execute(
            "SELECT COUNT(*) AS c FROM observations"
        ).fetchone()["c"]
        by_cat = {}
        for r in self._conn.execute(
            "SELECT category, COUNT(*) AS c, AVG(confidence) AS avg_conf "
            "FROM observations GROUP BY category"
        ).fetchall():
            by_cat[r["category"]] = {
                "count": r["c"],
                "avg_confidence": round(r["avg_conf"], 2),
            }
        requests = self._conn.execute(
            "SELECT COUNT(*) AS c FROM request_patterns"
        ).fetchone()["c"]
        auto_eligible = self._conn.execute(
            "SELECT COUNT(*) AS c FROM request_patterns WHERE frequency >= 3"
        ).fetchone()["c"]
        return {
            "total_observations": total,
            "by_category": by_cat,
            "request_patterns": requests,
            "auto_eligible_patterns": auto_eligible,
        }

    def decay_stale(self, days: int = 90) -> int:
        """Reduce confidence of observations not seen in N days."""
        cutoff = time.time() - (days * 86400)
        cur = self._conn.execute(
            """UPDATE observations
               SET confidence = MAX(0.1, confidence * 0.7)
               WHERE last_seen < ? AND confidence > 0.1""",
            (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()

    def _get_raw(self, observation_id: str):
        return self._conn.execute(
            "SELECT * FROM observations WHERE observation_id = ?", (observation_id,)
        ).fetchone()

    @staticmethod
    def _row_to_obs(row: sqlite3.Row) -> UserObservation:
        return UserObservation(
            observation_id=row["observation_id"],
            category=row["category"],
            content=row["content"],
            confidence=row["confidence"],
            frequency=row["frequency"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            context=row["context"],
            auto_action=row["auto_action"],
        )
