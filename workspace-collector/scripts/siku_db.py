#!/usr/bin/env python3
"""
收藏家（司库）数据库操作模块
封装持仓、交易、告警的增删改查
"""

import os
import json
import sqlite3
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _conn_positions():
    return sqlite3.connect(os.path.join(DATA_DIR, "positions.db"))


def _conn_transactions():
    return sqlite3.connect(os.path.join(DATA_DIR, "transactions.db"))


def _conn_alerts():
    return sqlite3.connect(os.path.join(DATA_DIR, "alerts.db"))


def load_clients():
    """加载客户信息"""
    path = os.path.join(DATA_DIR, "clients.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


# === 持仓操作 ===

def get_positions(client_id=None, category=None):
    """查询持仓，可选按客户或类别过滤"""
    conn = _conn_positions()
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM positions WHERE 1=1"
    params = []
    if client_id:
        query += " AND client_id = ?"
        params.append(client_id)
    if category:
        query += " AND category = ?"
        params.append(category)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_position(client_id, ts_code, stock_name, quantity, avg_cost,
                 stop_loss_pct=-10.0, take_profit_pct=20.0):
    """新增或更新持仓"""
    conn = _conn_positions()
    conn.execute("""
        INSERT INTO positions (client_id, ts_code, stock_name, quantity, avg_cost,
                               stop_loss_pct, take_profit_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(client_id, ts_code) DO UPDATE SET
            quantity = excluded.quantity,
            avg_cost = excluded.avg_cost,
            updated_at = datetime('now', 'localtime')
    """, (client_id, ts_code, stock_name, quantity, avg_cost, stop_loss_pct, take_profit_pct))
    conn.commit()
    conn.close()


def remove_position(client_id, ts_code):
    """移除持仓"""
    conn = _conn_positions()
    conn.execute("DELETE FROM positions WHERE client_id = ? AND ts_code = ?", (client_id, ts_code))
    conn.commit()
    conn.close()


# === 交易操作 ===

def add_transaction(client_id, ts_code, stock_name, direction, price, quantity, note=""):
    """记录一笔交易"""
    conn = _conn_transactions()
    amount = price * quantity
    conn.execute("""
        INSERT INTO transactions (client_id, ts_code, stock_name, direction, price, quantity, amount, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (client_id, ts_code, stock_name, direction, price, quantity, amount, note))
    conn.commit()
    conn.close()


def get_transactions(client_id=None, limit=20):
    """查询交易流水"""
    conn = _conn_transactions()
    conn.row_factory = sqlite3.Row
    if client_id:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE client_id = ? ORDER BY created_at DESC LIMIT ?",
            (client_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# === 告警操作 ===

def add_alert(client_id, ts_code, alert_type, trigger_price, current_price, message=""):
    """记录告警"""
    conn = _conn_alerts()
    conn.execute("""
        INSERT INTO alerts (client_id, ts_code, alert_type, trigger_price, current_price, message)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (client_id, ts_code, alert_type, trigger_price, current_price, message))
    conn.commit()
    conn.close()


def get_pending_alerts():
    """获取待处理的告警"""
    conn = _conn_alerts()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM alerts WHERE status = 'pending' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_alert_sent(alert_id):
    """标记告警已通知主席"""
    conn = _conn_alerts()
    conn.execute("UPDATE alerts SET status = 'sent', sent_to_chairman = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    print("=== 收藏家数据库模块测试 ===")
    print(f"数据目录: {DATA_DIR}")
    clients = load_clients()
    print(f"客户数量: {len(clients)}")
    for name in clients:
        print(f"  - {name} ({clients[name].get('alias','')})")
    print("模块就绪 ✅")
