import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DEFAULT_DB_PATH = os.environ.get(
    "REPOFINDER_DB", os.path.join(os.path.dirname(__file__), "..", "..", "repofinder.db")
)


def _get_db_path() -> str:
    return os.path.abspath(DEFAULT_DB_PATH)


@contextmanager
def get_db(db_path: str | None = None):
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | None = None):
    """Create tables if they don't exist."""
    with get_db(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watched_repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL,
                repo TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'github',
                origin_url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'alive',
                first_seen TEXT NOT NULL,
                last_checked TEXT,
                removed_at TEXT,
                UNIQUE(origin_url)
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id INTEGER NOT NULL REFERENCES watched_repos(id),
                checked_at TEXT NOT NULL,
                http_status INTEGER,
                was_alive INTEGER NOT NULL,
                FOREIGN KEY (repo_id) REFERENCES watched_repos(id)
            );

            CREATE INDEX IF NOT EXISTS idx_watched_status ON watched_repos(status);
            CREATE INDEX IF NOT EXISTS idx_watched_origin ON watched_repos(origin_url);
        """)


def add_repo(owner: str, repo: str, platform: str, origin_url: str, db_path: str | None = None) -> int:
    """Add a repo to the watch list. Returns the repo ID."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db(db_path) as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO watched_repos (owner, repo, platform, origin_url, first_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (owner, repo, platform, origin_url, now),
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Already exists
            row = conn.execute(
                "SELECT id FROM watched_repos WHERE origin_url = ?", (origin_url,)
            ).fetchone()
            return row["id"]


def list_repos(status: str | None = None, db_path: str | None = None) -> list[dict]:
    """List watched repos, optionally filtered by status."""
    with get_db(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM watched_repos WHERE status = ? ORDER BY removed_at DESC, last_checked DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM watched_repos ORDER BY status DESC, last_checked DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def update_repo_status(repo_id: int, alive: bool, http_status: int | None = None, db_path: str | None = None):
    """Update a repo's status after a scan check."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db(db_path) as conn:
        if alive:
            conn.execute(
                "UPDATE watched_repos SET status = 'alive', last_checked = ? WHERE id = ?",
                (now, repo_id),
            )
        else:
            conn.execute(
                "UPDATE watched_repos SET status = 'removed', last_checked = ?, "
                "removed_at = COALESCE(removed_at, ?) WHERE id = ?",
                (now, now, repo_id),
            )
        conn.execute(
            "INSERT INTO scan_log (repo_id, checked_at, http_status, was_alive) VALUES (?, ?, ?, ?)",
            (repo_id, now, http_status, int(alive)),
        )


def get_repo_history(repo_id: int, db_path: str | None = None) -> list[dict]:
    """Get scan history for a repo."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM scan_log WHERE repo_id = ? ORDER BY checked_at DESC LIMIT 50",
            (repo_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats(db_path: str | None = None) -> dict:
    """Get summary stats."""
    with get_db(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM watched_repos").fetchone()[0]
        alive = conn.execute("SELECT COUNT(*) FROM watched_repos WHERE status = 'alive'").fetchone()[0]
        removed = conn.execute("SELECT COUNT(*) FROM watched_repos WHERE status = 'removed'").fetchone()[0]
        return {"total": total, "alive": alive, "removed": removed}
