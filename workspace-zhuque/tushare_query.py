#!/usr/bin/env python3
"""
Tushare 数据查询工具 —— 委员会专用版
============================================
用途: 供 Orobas 数据和委员会各方调用，获取 A 股行情、基础信息等。

当前积分: 123 分
可用接口: daily (非复权日线), stock_basic, new_share, shibor_lpr
2000+ 分接口: 财务数据 / 资金流等暂不可用

用法:
  python3 tushare_query.py daily --code 600519.SH --start 20260101 --end 20260512
  python3 tushare_query.py daily --code 000001.SZ --days 20
  python3 tushare_query.py stock_basic
  python3 tushare_query.py new_share
"""

import os
import sys
import time
import json
import argparse
import pandas as pd

TOKEN = "14d17af9a3ab55306b3f7c6ec4d01d140fbddc43a721b2e175fb8dfb"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tushare_cache")

os.environ["TUSHARE_TOKEN"] = TOKEN

import tushare as ts
ts.set_token(TOKEN)
pro = ts.pro_api()


def query_daily(ts_code, start_date=None, end_date=None, days=None):
    """日线行情（非复权）"""
    if days and not start_date:
        from datetime import datetime, timedelta
        end = datetime.now()
        start = end - timedelta(days=days)
        start_date = start.strftime("%Y%m%d")
        end_date = end.strftime("%Y%m%d")

    return pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)


def query_stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,list_date", use_cache=True):
    """股票基础信息（带本地缓存，避免频率限制）"""
    cache_file = os.path.join(CACHE_DIR, "stock_basic.csv")
    if use_cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        if os.path.exists(cache_file):
            mod_time = os.path.getmtime(cache_file)
            age_hours = (time.time() - mod_time) / 3600
            if age_hours < 24:  # 缓存24小时有效
                df = pd.read_csv(cache_file)
                print(f"[缓存] 使用本地缓存 (age={age_hours:.1f}h)", file=sys.stderr)
                return df
    
    df = pro.stock_basic(exchange=exchange, list_status=list_status, fields=fields)
    if use_cache and len(df) > 0:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_csv(cache_file, index=False)
        print(f"[缓存] 已保存到本地", file=sys.stderr)
    return df


def query_new_share():
    """IPO新股列表"""
    return pro.new_share()


def query_shibor_lpr():
    """LPR利率"""
    return pro.shibor_lpr()


def search_stock(keyword):
    """根据名称或代码模糊搜索股票"""
    df = query_stock_basic()
    mask = df["name"].str.contains(keyword, na=False) | df["symbol"].str.contains(keyword, na=False) | df["ts_code"].str.contains(keyword.upper(), na=False)
    return df[mask]


def resolve_code(name_or_code):
    """将股票名称/代码解析为标准 ts_code"""
    # If already a ts_code format
    if "." in name_or_code and len(name_or_code.split(".")[0]) == 6:
        return name_or_code

    # Try as symbol
    df = query_stock_basic()
    # By symbol
    match = df[df["symbol"] == name_or_code]
    if len(match) > 0:
        return match.iloc[0]["ts_code"]
    # By name
    match = df[df["name"] == name_or_code]
    if len(match) == 1:
        return match.iloc[0]["ts_code"]
    if len(match) > 1:
        # Multiple matches, try exact symbol
        match2 = df[df["symbol"] == name_or_code.zfill(6)]
        if len(match2) > 0:
            return match2.iloc[0]["ts_code"]
    return None


def main():
    parser = argparse.ArgumentParser(description="Tushare 数据查询工具")
    sub = parser.add_subparsers(dest="command", help="查询类型")

    # daily
    p_daily = sub.add_parser("daily", help="日线行情")
    p_daily.add_argument("--code", required=True, help="股票代码 (如 600519.SH)")
    p_daily.add_argument("--start", help="开始日期 YYYYMMDD")
    p_daily.add_argument("--end", help="结束日期 YYYYMMDD")
    p_daily.add_argument("--days", type=int, help="最近 N 天数据")

    # stock_basic
    p_basic = sub.add_parser("stock_basic", help="股票基础信息")
    p_basic.add_argument("--exchange", default="", help="交易所 SSE/SZSE/BSE")
    p_basic.add_argument("--list_status", default="L", help="L上市 D退市 P暂停")

    # search
    p_search = sub.add_parser("search", help="搜索股票")
    p_search.add_argument("keyword", help="名称/代码关键字")

    # resolve
    p_resolve = sub.add_parser("resolve", help="解析股票代码")
    p_resolve.add_argument("name", help="股票名称或代码")

    # list available
    sub.add_parser("interfaces", help="列出当前可用接口和积分情况")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "daily":
            df = query_daily(args.code, args.start, args.end, args.days)
            print(df.to_string(index=False))

        elif args.command == "stock_basic":
            df = query_stock_basic(args.exchange, args.list_status)
            print(df.to_string(index=False))

        elif args.command == "search":
            df = search_stock(args.keyword)
            if len(df) > 0:
                print(df[["ts_code", "symbol", "name", "area", "industry", "list_date"]].to_string(index=False))
            else:
                print(f"未找到匹配: {args.keyword}")

        elif args.command == "resolve":
            code = resolve_code(args.name)
            if code:
                print(code)
            else:
                print(f"无法解析: {args.name}")

        elif args.command == "new_share":
            df = query_new_share()
            print(df.to_string(index=False))

        elif args.command == "interfaces":
            print("=== Tushare 接口状态 (123积分) ===")
            print("✅ stock_basic  - 股票基础信息 (0分)")
            print("✅ daily        - 日线行情 (120分)")
            print("✅ new_share    - IPO新股列表 (120分)")
            print("✅ shibor_lpr   - LPR利率 (120分)")
            print("✅ libor        - Libor利率 (120分)")
            print("✅ hibor        - Hibor利率 (120分)")
            print("")
            print("❌ fina_indicator - 财务指标 (需2000分)")
            print("❌ income        - 利润表 (需2000分)")
            print("❌ balancesheet  - 资产负债表 (需2000分)")
            print("❌ cashflow      - 现金流量表 (需2000分)")
            print("❌ daily_basic   - 每日指标 (需2000分)")
            print("❌ moneyflow     - 资金流向 (需2000分)")
            print("❌ index_daily   - 指数行情 (需2000分)")
            print("❌ top_list      - 龙虎榜 (需2000分)")
            print("")
            print("调用限制: 每分钟50次, 每天8000次")

    except Exception as e:
        print(f"❌ 查询失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
