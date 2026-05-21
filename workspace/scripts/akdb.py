#!/usr/bin/env python3
"""
AKShare 数据缓存模块 (SQLite)
投资委员会数据基础设施
conda env: py39

设计说明：
- 两层缓存：查询级缓存（cache 表）+ 市场快照（snapshots 表）
- TTL 机制：行情数据 T+0 过期，财务数据 7天，宏观数据 1天
- 定时任务（cron）负责在开/收盘批量预取数据写入 cache，查询时直接读
- 脚本直调作为兜底：cache 未命中或过期时 → 调 API → 写入 cache → 返回
"""

import json
import os
import sqlite3
import time
from datetime import datetime, date, timedelta
from typing import Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".akcache")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "akshare_cache.db")

# TTL 配置（单位：秒）
TTL = {
    "realtime": 3600 * 6,         # 实时行情 → 6小时（盘中足够）
    "finance": 86400 * 7,         # 财务数据 → 7天
    "info": 86400,                # 基本信息 → 1天
    "history": 86400,             # 历史K线 → 1天
    "index": 3600 * 6,            # 指数行情 → 6小时
    "macro": 86400,               # 宏观数据 → 1天
    "north": 3600 * 6,            # 北向资金 → 6小时
    "snapshot": 86400,            # 市场快照 → 1天
    "default": 3600,              # 默认 → 1小时
}

# ──────────── 数据库初始化 ────────────


def get_db() -> sqlite3.Connection:
    """获取数据库连接（线程安全，WAL模式）"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化数据库表结构"""
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            data_type TEXT NOT NULL DEFAULT 'default',
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_type TEXT NOT NULL,   -- 'open' | 'close' | 'custom'
            created_at REAL NOT NULL,
            data TEXT NOT NULL             -- JSON blob of all cached data at snapshot time
        );

        CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
        CREATE INDEX IF NOT EXISTS idx_snapshots_type ON snapshots(snapshot_type);
        """
    )
    conn.commit()
    conn.close()


# ──────────── 缓存操作 ────────────


def _make_key(category: str, *parts: str) -> str:
    """生成缓存键，如 'realtime_600519'"""
    clean = [p.replace(":", "").replace(" ", "_") for p in parts if p]
    return f"{category}_{'_'.join(clean)}"


def cache_get(category: str, *parts: str) -> Optional[Any]:
    """读取缓存，过期返回 None"""
    key = _make_key(category, *parts)
    conn = get_db()
    row = conn.execute(
        "SELECT data, expires_at FROM cache WHERE key = ?", (key,)
    ).fetchone()
    conn.close()

    if row is None:
        return None

    now = time.time()
    if row["expires_at"] < now:
        # 过期，删除并返回 None
        conn = get_db()
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()
        conn.close()
        return None

    try:
        return json.loads(row["data"])
    except (json.JSONDecodeError, TypeError):
        return None


def cache_set(category: str, data: Any, *parts: str, ttl: int = None) -> None:
    """写入缓存"""
    key = _make_key(category, *parts)
    if ttl is None:
        ttl = TTL.get(category, TTL["default"])

    now = time.time()
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO cache (key, data, data_type, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (key, json.dumps(data, ensure_ascii=False, default=str), category, now, now + ttl),
    )
    conn.commit()
    conn.close()


def cache_delete(category: str, *parts: str) -> None:
    """删除指定缓存"""
    key = _make_key(category, *parts)
    conn = get_db()
    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
    conn.commit()
    conn.close()


def cache_clear_expired() -> int:
    """清除所有过期缓存，返回清除数量"""
    conn = get_db()
    now = time.time()
    count = conn.execute("DELETE FROM cache WHERE expires_at < ?", (now,)).rowcount
    conn.commit()
    conn.close()
    return count


def cache_clear_all() -> int:
    """清空所有缓存"""
    conn = get_db()
    count = conn.execute("DELETE FROM cache").rowcount
    conn.execute("DELETE FROM snapshots")
    conn.commit()
    conn.close()
    return count


def cache_stats() -> dict:
    """缓存统计"""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM cache").fetchone()["c"]
    expired = conn.execute("SELECT COUNT(*) as c FROM cache WHERE expires_at < ?",
                          (time.time(),)).fetchone()["c"]
    snapshots = conn.execute("SELECT COUNT(*) as c FROM snapshots").fetchone()["c"]
    conn.close()
    return {
        "total": total,
        "expired": expired,
        "valid": total - expired,
        "snapshots": snapshots,
        "db_path": DB_PATH,
    }


# ──────────── 快照操作 ────────────


def save_snapshot(snapshot_type: str, data: dict) -> None:
    """保存市场快照"""
    conn = get_db()
    conn.execute(
        "INSERT INTO snapshots (snapshot_type, created_at, data) VALUES (?, ?, ?)",
        (snapshot_type, time.time(), json.dumps(data, ensure_ascii=False, default=str)),
    )
    # 清理旧快照，只保留最近 30 条
    conn.execute(
        """DELETE FROM snapshots WHERE id NOT IN (
            SELECT id FROM snapshots ORDER BY id DESC LIMIT 30
        )"""
    )
    conn.commit()
    conn.close()


def get_recent_snapshots(snapshot_type: str = None, limit: int = 5) -> list[dict]:
    """获取最近快照"""
    conn = get_db()
    if snapshot_type:
        rows = conn.execute(
            "SELECT * FROM snapshots WHERE snapshot_type = ? ORDER BY id DESC LIMIT ?",
            (snapshot_type, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "snapshot_type": row["snapshot_type"],
            "created_at": datetime.fromtimestamp(row["created_at"]).isoformat(),
            "data": json.loads(row["data"]),
        })
    return results


# ──────────── 初始化 ────────────

# 模块导入时自动初始化
init_db()
