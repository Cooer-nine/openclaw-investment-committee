#!/usr/bin/env python3
"""
AKShare 定时数据更新脚本
投资委员会数据基础设施
conda env: py39

运行方式（通过 cron）：
  conda run -n py39 python scripts/akcron.py open    # 09:25 开盘前
  conda run -n py39 python scripts/akcron.py close   # 15:05 收盘后
  conda run -n py39 python scripts/akcron.py status  # 查看缓存状态
  conda run -n py39 python scripts/akcron.py clear   # 清空缓存
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Any

# 确保能找到同目录下的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import akdb

# ──────────── 常用标的列表（可扩展） ────────────

# 主要指数
MAJOR_INDEXES = ["000001", "399001", "399006", "000688", "000300", "000016", "000905"]

# 常查 A 股（按市值/关注度筛选）
WATCHLIST_A = [
    "600519",  # 贵州茅台
    "000858",  # 五粮液
    "601318",  # 中国平安
    "600036",  # 招商银行
    "000333",  # 美的集团
    "600276",  # 恒瑞医药
    "300750",  # 宁德时代
    "002594",  # 比亚迪
    "601012",  # 隆基绿能
    "600900",  # 长江电力
    "000001",  # 平安银行
    "002415",  # 海康威视
    "600887",  # 伊利股份
    "603259",  # 药明康德
    "300059",  # 东方财富
]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ──────────── 数据预取函数 ────────────


def prefetch_indexes() -> list[dict]:
    """预取大盘指数行情"""
    from akshare_data import _gt_fetch

    codes = [f"sh{c}" if str(c).startswith(("6", "9", "0")) else f"sz{c}" for c in MAJOR_INDEXES]
    results = _gt_fetch(*codes)
    if results:
        akdb.cache_set("index", results, "all")
        # 同时写入 realtime_major，供 stock_realtime(None) 读取
        akdb.cache_set("realtime", results, "major")
        log(f"✓ 指数行情: {len(results)} 条")
    else:
        log("✗ 指数行情: 获取失败")
    return results


def prefetch_stocks(codes: list[str]) -> list[dict]:
    """预取个股行情"""
    from akshare_data import _gt_fetch

    gt_codes = []
    for c in codes:
        c = c.strip()
        if c.startswith(("6", "9")):
            gt_codes.append(f"sh{c}")
        else:
            gt_codes.append(f"sz{c}")

    results = _gt_fetch(*gt_codes)
    if results:
        for r in results:
            code = r.get("code", "")
            akdb.cache_set("realtime", r, code)
        log(f"✓ 个股行情: {len(results)} 条")
    else:
        log("✗ 个股行情: 获取失败")
    return results


def prefetch_north() -> None:
    """预取北向资金"""
    try:
        import akshare as ak

        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is not None and not df.empty:
            records = df.to_dict(orient="records")
            akdb.cache_set("north", records, "all")
            log(f"✓ 北向资金: {len(records)} 条")
        else:
            log("✗ 北向资金: 数据为空")
    except Exception as e:
        log(f"✗ 北向资金: {e}")


def prefetch_financials(codes: list[str]) -> int:
    """预取财务数据摘要"""
    count = 0
    try:
        import akshare as ak

        for code in codes:
            try:
                df = ak.stock_financial_abstract(symbol=code)
                if df is not None and not df.empty:
                    metrics = {}
                    for _, r in df[df["选项"] == "常用指标"].iterrows():
                        name = r["指标"]
                        cols = [c for c in df.columns if c not in ["选项", "指标"]][:2]
                        metrics[name] = {c: r[c] for c in cols}
                    akdb.cache_set("finance", metrics, code)
                    count += 1
            except Exception:
                continue
        log(f"✓ 财务数据: {count} 只")
    except Exception as e:
        log(f"✗ 财务数据: {e}")
    return count


def prefetch_basic_info(codes: list[str]) -> int:
    """预取基本信息"""
    count = 0
    from akshare_data import _gt_fetch

    for code in codes:
        prefix = "sh" if str(code).startswith(("6", "9")) else "sz"
        gt = _gt_fetch(f"{prefix}{code}")
        if gt:
            r = gt[0]
            info = {
                "名称": r.get("name"),
                "代码": r.get("code"),
                "最新价": r.get("price"),
                "昨收": r.get("prev_close"),
                "今开": r.get("open"),
                "最高": r.get("high"),
                "最低": r.get("low"),
                "涨跌": r.get("change"),
                "涨跌幅": r.get("change_pct"),
                "成交量(手)": r.get("volume_hand"),
                "成交额": r.get("turnover"),
                "市盈率": r.get("pe"),
            }
            akdb.cache_set("info", info, code)
            count += 1
    log(f"✓ 基本信息: {count} 只")
    return count


# ──────────── 快照 ────────────


def take_snapshot(snapshot_type: str, codes: list[str]) -> None:
    """保存当前市场快照"""
    from akshare_data import _gt_fetch

    index_codes = [f"sh{c}" if str(c).startswith(("6", "9", "0")) else f"sz{c}" for c in MAJOR_INDEXES]
    stock_codes = []
    for c in codes:
        if c.startswith(("6", "9")):
            stock_codes.append(f"sh{c}")
        else:
            stock_codes.append(f"sz{c}")

    indexes = _gt_fetch(*index_codes)
    stocks = _gt_fetch(*stock_codes)

    snapshot = {
        "type": snapshot_type,
        "time": datetime.now().isoformat(),
        "indexes": indexes,
        "stocks": stocks,
        "cache_stats": akdb.cache_stats(),
    }
    akdb.save_snapshot(snapshot_type, snapshot)
    log(f"✓ 快照已保存: {snapshot_type}")


# ──────────── Cron 入口 ────────────


def run_open() -> None:
    """开盘前定时任务 (09:25)"""
    log("═══ 开盘前批量预取 ═══")
    start = time.time()

    # 1. 指数行情
    prefetch_indexes()

    # 2. 关注列表个股行情 + 基本信息
    prefetch_stocks(WATCHLIST_A)
    prefetch_basic_info(WATCHLIST_A)

    # 3. 北向资金
    prefetch_north()

    # 4. 保存开盘快照
    take_snapshot("open", WATCHLIST_A)

    elapsed = time.time() - start
    log(f"═══ 完成 ({elapsed:.1f}s) ═══")
    print()
    stats = akdb.cache_stats()
    print(f"缓存统计: 有效 {stats['valid']} 条 / 过期 {stats['expired']} 条")


def run_close() -> None:
    """收盘后定时任务 (15:05)"""
    log("═══ 收盘后批量更新 ═══")
    start = time.time()

    # 1. 更新最终行情
    prefetch_indexes()
    prefetch_stocks(WATCHLIST_A)

    # 2. 更新基本信息（收盘价已变）
    prefetch_basic_info(WATCHLIST_A)

    # 3. 北向资金（收盘后数据完整）
    prefetch_north()

    # 4. 保存收盘快照
    take_snapshot("close", WATCHLIST_A)

    elapsed = time.time() - start
    log(f"═══ 完成 ({elapsed:.1f}s) ═══")
    print()
    stats = akdb.cache_stats()
    print(f"缓存统计: 有效 {stats['valid']} 条 / 过期 {stats['expired']} 条")
    print(f"快照数: {stats['snapshots']}")


def show_status() -> None:
    """查看缓存状态"""
    stats = akdb.cache_stats()
    print(f"数据库: {stats['db_path']}")
    print(f"缓存总数: {stats['total']}")
    print(f"有效: {stats['valid']}")
    print(f"过期: {stats['expired']}")
    print(f"快照数: {stats['snapshots']}")
    print()
    snaps = akdb.get_recent_snapshots(limit=3)
    for s in snaps:
        ns = s["data"].get("stocks", [])
        ni = s["data"].get("indexes", [])
        print(f"  [{s['snapshot_type']}] {s['created_at']} — 指数{len(ni)}条 个股{len(ns)}条")


# ──────────── CLI ────────────


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: conda run -n py39 python scripts/akcron.py <open|close|status|clear>\n")
        print("  open   — 开盘前批量预取 (09:25)")
        print("  close  — 收盘后批量更新 (15:05)")
        print("  status — 查看缓存状态")
        print("  clear  — 清空全部缓存")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "open":
        run_open()
    elif cmd == "close":
        run_close()
    elif cmd == "status":
        show_status()
    elif cmd == "clear":
        count = akdb.cache_clear_all()
        print(f"已清空 {count} 条缓存")
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
