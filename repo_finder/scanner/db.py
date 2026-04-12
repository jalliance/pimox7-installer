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
                stars INTEGER DEFAULT 0,
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

            -- Tracks discover crawl progress so it can resume
            CREATE TABLE IF NOT EXISTS discover_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_watched_status ON watched_repos(status);
            CREATE INDEX IF NOT EXISTS idx_watched_origin ON watched_repos(origin_url);
            CREATE INDEX IF NOT EXISTS idx_watched_stars ON watched_repos(stars);
            CREATE INDEX IF NOT EXISTS idx_watched_last_checked ON watched_repos(last_checked);
        """)

        # Migration: add stars column if missing (for existing DBs)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(watched_repos)").fetchall()}
        if "stars" not in cols:
            conn.execute("ALTER TABLE watched_repos ADD COLUMN stars INTEGER DEFAULT 0")


def add_repo(
    owner: str,
    repo: str,
    platform: str,
    origin_url: str,
    stars: int = 0,
    db_path: str | None = None,
) -> int:
    """Add a repo to the watch list. Returns the repo ID."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db(db_path) as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO watched_repos (owner, repo, platform, origin_url, stars, first_seen) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (owner, repo, platform, origin_url, stars, now),
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Already exists — update stars if higher
            conn.execute(
                "UPDATE watched_repos SET stars = MAX(stars, ?) WHERE origin_url = ?",
                (stars, origin_url),
            )
            row = conn.execute(
                "SELECT id FROM watched_repos WHERE origin_url = ?", (origin_url,)
            ).fetchone()
            return row["id"]


def add_repos_bulk(
    repos: list[dict], db_path: str | None = None
) -> int:
    """Bulk-add repos. Each dict needs: owner, repo, platform, origin_url, stars.
    Returns number of newly inserted repos.
    """
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with get_db(db_path) as conn:
        for r in repos:
            try:
                conn.execute(
                    "INSERT INTO watched_repos (owner, repo, platform, origin_url, stars, first_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (r["owner"], r["repo"], r["platform"], r["origin_url"], r.get("stars", 0), now),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                conn.execute(
                    "UPDATE watched_repos SET stars = MAX(stars, ?) WHERE origin_url = ?",
                    (r.get("stars", 0), r["origin_url"]),
                )
    return inserted


def list_repos(
    status: str | None = None,
    limit: int = 0,
    offset: int = 0,
    order_by: str = "stars DESC",
    db_path: str | None = None,
) -> list[dict]:
    """List watched repos with optional filtering, pagination, and ordering."""
    with get_db(db_path) as conn:
        query = "SELECT * FROM watched_repos"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += f" ORDER BY {order_by}"
        if limit > 0:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def count_repos(status: str | None = None, db_path: str | None = None) -> int:
    """Count repos, optionally filtered by status."""
    with get_db(db_path) as conn:
        if status:
            return conn.execute(
                "SELECT COUNT(*) FROM watched_repos WHERE status = ?", (status,)
            ).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM watched_repos").fetchone()[0]


def get_unchecked_repos(
    limit: int = 1000, db_path: str | None = None
) -> list[dict]:
    """Get repos that need checking, prioritizing never-checked and stale ones."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM watched_repos "
            "WHERE status = 'alive' "
            "ORDER BY last_checked ASC NULLS FIRST "
            "LIMIT ?",
            (limit,),
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


# --- Discover state helpers ---

def get_discover_state(key: str, default: str = "", db_path: str | None = None) -> str:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT value FROM discover_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_discover_state(key: str, value: str, db_path: str | None = None):
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO discover_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
