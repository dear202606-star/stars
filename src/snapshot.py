"""SQLite 历史快照模块：记录已推荐过的仓库，用于跨天去重。"""

import os
import sqlite3
from datetime import datetime, date, timezone


def get_conn(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    # timeout: 等待锁 30 秒；WAL 模式：读写不互斥；busy_timeout: 忙等待
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recommended (
            full_name TEXT PRIMARY KEY,
            repo_id INTEGER,
            stars INTEGER,
            language TEXT,
            recommended_at TEXT,
            article_date TEXT
        )
    """)
    return conn


def is_recommended(conn: sqlite3.Connection, full_name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM recommended WHERE full_name=?", (full_name,))
    return cur.fetchone() is not None


def mark_recommended(conn: sqlite3.Connection, repo: dict,
                     article_date: str = None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO recommended"
        "(full_name, repo_id, stars, language, recommended_at, article_date) "
        "VALUES (?,?,?,?,?,?)",
        (repo["full_name"], repo.get("id"), repo.get("stargazers_count"),
         repo.get("language"), datetime.now(timezone.utc).isoformat(),
         article_date or date.today().isoformat())
    )
    conn.commit()


def dedupe(conn: sqlite3.Connection, candidates: list, top_n: int) -> list:
    """优先返回未推荐过的；若不足 top_n，则用已推荐过的补齐，保证数量。"""
    fresh, used = [], []
    for r in candidates:
        (fresh if not is_recommended(conn, r["full_name"]) else used).append(r)
    result = fresh[:top_n]
    if len(result) < top_n:
        result.extend(used[: top_n - len(result)])
    return result
