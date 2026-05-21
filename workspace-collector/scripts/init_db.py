#!/usr/bin/env python3
"""
收藏家（司库）数据库初始化脚本
创建 positions.db, transactions.db, alerts.db
"""

import os
import sqlite3
import json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "models"), exist_ok=True)


def init_positions():
    """持仓表"""
    conn = sqlite3.connect(os.path.join(DATA_DIR, "positions.db"))
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            direction TEXT DEFAULT 'long',
            quantity REAL NOT NULL,
            avg_cost REAL NOT NULL,
            stop_loss_pct REAL DEFAULT -10.0,
            take_profit_pct REAL DEFAULT 20.0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(client_id, ts_code)
        )
    """)
    conn.commit()
    conn.close()
    print("✅ positions.db 初始化完成")


def init_transactions():
    """交易流水表"""
    conn = sqlite3.connect(os.path.join(DATA_DIR, "transactions.db"))
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('buy', 'sell')),
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    conn.close()
    print("✅ transactions.db 初始化完成")


def init_alerts():
    """告警日志表"""
    conn = sqlite3.connect(os.path.join(DATA_DIR, "alerts.db"))
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            alert_type TEXT NOT NULL CHECK(alert_type IN ('stop_loss', 'take_profit', 'info')),
            trigger_price REAL,
            current_price REAL,
            message TEXT,
            status TEXT DEFAULT 'pending',
            sent_to_chairman INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    conn.close()
    print("✅ alerts.db 初始化完成")


def init_clients():
    """客户信息文件"""
    clients_file = os.path.join(DATA_DIR, "clients.json")
    if not os.path.exists(clients_file):
        clients = {
            "仇行": {"open_id": "ou_0a6d0d4bad3cfef68690fd24fc8389eb", "alias": "仇文菁"},
            "檀博": {"open_id": "ou_46b265822c5ce5659132a7f1080801f6", "alias": "TTT"},
            "总工": {"open_id": "ou_985a7ae4904267d555e32b6ff79185c6", "alias": "用户436105"}
        }
        with open(clients_file, "w") as f:
            json.dump(clients, f, ensure_ascii=False, indent=2)
        print("✅ clients.json 初始化完成（含3位客户）")
    else:
        print("✅ clients.json 已存在")


if __name__ == "__main__":
    print("=== 收藏家数据库初始化 ===")
    init_positions()
    init_transactions()
    init_alerts()
    init_clients()
    print("\n所有数据库已就绪。")
