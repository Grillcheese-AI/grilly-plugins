"""
Global knowledge store for elephant-coder.

Stores framework references, session summaries, research notes, and
coding idioms that persist across ALL projects.

Location: ~/.elephant-coder/global/knowledge.db
"""

import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("elephant-coder.global")


class GlobalKnowledgeStore:
    """SQLite store for cross-project knowledge."""

    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            base_dir = str(Path.home() / ".elephant-coder" / "global")
        Path(base_dir).mkdir(parents=True, exist_ok=True)
        db_path = Path(base_dir) / "knowledge.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS frameworks (
                name TEXT PRIMARY KEY,
                repo_path TEXT,
                github TEXT,
                api_map TEXT NOT NULL DEFAULT '{}',
                quick_start TEXT NOT NULL DEFAULT '',
                differences TEXT NOT NULL DEFAULT '[]',
                updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                summary TEXT NOT NULL,
                tasks_completed TEXT NOT NULL DEFAULT '[]',
                tasks_remaining TEXT NOT NULL DEFAULT '[]',
                timestamp REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                summary TEXT NOT NULL,
                source TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                relevance_to TEXT NOT NULL DEFAULT '[]',
                discovered_in_session TEXT,
                actionable INTEGER DEFAULT 0,
                potential_task TEXT,
                timestamp REAL NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                topic, summary, tags
            );
            CREATE TABLE IF NOT EXISTS idioms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                context TEXT NOT NULL,
                project TEXT,
                frequency INTEGER DEFAULT 1,
                timestamp REAL NOT NULL
            );
        """)
        self._conn.commit()

    # --- Frameworks ---
    def save_framework(self, name, repo_path, github, api_map, quick_start, differences):
        self._conn.execute(
            "INSERT OR REPLACE INTO frameworks (name, repo_path, github, api_map, quick_start, differences, updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, repo_path, github, json.dumps(api_map), quick_start, json.dumps(differences), time.time()))
        self._conn.commit()

    def get_framework(self, name):
        row = self._conn.execute("SELECT * FROM frameworks WHERE name = ?", (name,)).fetchone()
        if not row: return None
        return {"name": row["name"], "repo_path": row["repo_path"], "github": row["github"],
                "api_map": json.loads(row["api_map"]), "quick_start": row["quick_start"],
                "differences": json.loads(row["differences"])}

    def get_all_frameworks(self):
        rows = self._conn.execute("SELECT * FROM frameworks").fetchall()
        return [{"name": r["name"], "repo_path": r["repo_path"], "github": r["github"],
                 "api_map": json.loads(r["api_map"]), "quick_start": r["quick_start"],
                 "differences": json.loads(r["differences"])} for r in rows]

    # --- Sessions ---
    def save_session_summary(self, project, summary, tasks_completed=None, tasks_remaining=None):
        self._conn.execute(
            "INSERT INTO sessions (project, summary, tasks_completed, tasks_remaining, timestamp) VALUES (?, ?, ?, ?, ?)",
            (project, summary, json.dumps(tasks_completed or []), json.dumps(tasks_remaining or []), time.time()))
        self._conn.commit()

    def get_recent_sessions(self, project, limit=5):
        rows = self._conn.execute("SELECT * FROM sessions WHERE project = ? ORDER BY timestamp DESC LIMIT ?", (project, limit)).fetchall()
        return [{"project": r["project"], "summary": r["summary"],
                 "tasks_completed": json.loads(r["tasks_completed"]),
                 "tasks_remaining": json.loads(r["tasks_remaining"]),
                 "timestamp": r["timestamp"]} for r in rows]

    # --- Research Notes ---
    def save_note(self, topic, summary, source=None, tags=None, relevance_to=None, actionable=False, potential_task=None):
        cur = self._conn.execute(
            "INSERT INTO notes (topic, summary, source, tags, relevance_to, actionable, potential_task, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (topic, summary, source, json.dumps(tags or []), json.dumps(relevance_to or []), int(actionable), potential_task, time.time()))
        note_id = cur.lastrowid
        self._conn.execute("INSERT INTO notes_fts (rowid, topic, summary, tags) VALUES (?, ?, ?, ?)",
                          (note_id, topic, summary, " ".join(tags or [])))
        self._conn.commit()
        return note_id

    def search_notes(self, query, limit=10):
        safe_query = query.replace('"', '""')
        try:
            rows = self._conn.execute(
                "SELECT n.* FROM notes n JOIN notes_fts fts ON n.id = fts.rowid WHERE notes_fts MATCH ? ORDER BY bm25(notes_fts) ASC LIMIT ?",
                (f'"{safe_query}"', limit)).fetchall()
        except sqlite3.OperationalError:
            like = f"%{query}%"
            rows = self._conn.execute("SELECT * FROM notes WHERE topic LIKE ? OR summary LIKE ? LIMIT ?", (like, like, limit)).fetchall()
        return [{"id": r["id"], "topic": r["topic"], "summary": r["summary"], "source": r["source"],
                 "tags": json.loads(r["tags"]), "relevance_to": json.loads(r["relevance_to"]),
                 "actionable": bool(r["actionable"]), "potential_task": r["potential_task"],
                 "timestamp": r["timestamp"]} for r in rows]

    def get_notes_by_tags(self, tags, limit=20):
        results = []
        seen_ids = set()
        for tag in tags:
            rows = self._conn.execute("SELECT * FROM notes WHERE tags LIKE ? ORDER BY timestamp DESC LIMIT ?",
                                      (f'%"{tag}"%', limit)).fetchall()
            for r in rows:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    results.append({"id": r["id"], "topic": r["topic"], "summary": r["summary"],
                                   "source": r["source"], "tags": json.loads(r["tags"]), "timestamp": r["timestamp"]})
        return results[:limit]

    # --- Idioms ---
    def save_idiom(self, pattern, context, project=None):
        existing = self._conn.execute("SELECT id, frequency FROM idioms WHERE pattern = ? AND context = ?", (pattern, context)).fetchone()
        if existing:
            self._conn.execute("UPDATE idioms SET frequency = frequency + 1 WHERE id = ?", (existing["id"],))
        else:
            self._conn.execute("INSERT INTO idioms (pattern, context, project, timestamp) VALUES (?, ?, ?, ?)",
                              (pattern, context, project, time.time()))
        self._conn.commit()

    def get_idioms(self, project=None, limit=20):
        if project:
            rows = self._conn.execute("SELECT * FROM idioms WHERE project = ? ORDER BY frequency DESC LIMIT ?", (project, limit)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM idioms ORDER BY frequency DESC LIMIT ?", (limit,)).fetchall()
        return [{"pattern": r["pattern"], "context": r["context"], "frequency": r["frequency"], "project": r["project"]} for r in rows]

    def close(self):
        self._conn.close()
