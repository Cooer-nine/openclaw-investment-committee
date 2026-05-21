#!/usr/bin/env python3
"""
AKShare 数据查询脚本 — 投资委员会数据基础设施
conda env: py39 (Python 3.9)

数据流：
  Cron (09:25/15:05) ──exec──→ akcron.py ──批量预取──→ SQLite 缓存
  Orobas/委员 查询 ──→ 本脚本 ──→ SQLite 缓存（命中 && 未过期 → 直返）
                                   └─ 未命中/过期 → 调 API → 写缓存 → 返回

数据源优先级（阿里云服务器环境实测）：
  1. SQLite 缓存（优先）
  2. Tencent GT API (qt.gtimg.cn) — 实时行情 ✅ 可靠
  3. Tencent K-line API (web.ifzq.gtimg.cn) — K线数据 ✅ 可靠
  4. AKShare 财务接口 — 偶发失败，带重试
  5. SearXNG/web_fetch — 兜底搜索查询
"""

import json
import os
import re
import subprocess
import sys
import argparse
from datetime import datetime, date, timedelta
from typing import Any, Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import akdb

# ──────────── 工具函数 ────────────


def json_serialize(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)


def output(data: Any, fmt: str = "text") -> None:
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, default=json_serialize, indent=2))
    else:
        print(data)


def _gt_code(code: str) -> str:
    """将股票代码转为 Tencent GT API 格式"""
    code = code.strip()
    if code.startswith(("6", "9")):
        return f"sh{code}"
    if code.startswith(("0", "3")):
        return f"sz{code}"
    return code


# ──────────── 腾讯 GT API (reliable from Alibaba Cloud) ────────────


def _gt_fetch(*codes: str) -> list[dict]:
    """通过 Tencent GT API 获取股票/指数实时数据"""
    code_str = ",".join(str(c) for c in codes)
    cmd = [
        "curl", "-s", "--connect-timeout", "5", "--max-time", "10",
        f"https://qt.gtimg.cn/q={code_str}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=15)
        if r.returncode != 0 or not r.stdout:
            return []
        text = r.stdout.decode("gbk", errors="replace")
        return _gt_parse(text)
    except Exception:
        return []


def _gt_parse(raw: str) -> list[dict]:
    """解析 Tencent GT API 返回的 v_xxx 格式数据"""
    results = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        m = re.search(r'"(.+)"', line)
        if not m:
            continue
        parts = m.group(1).split("~")
        if len(parts) < 40:
            continue
        try:
            change_pct = float(parts[32]) if parts[32] else 0.0
        except ValueError:
            change_pct = 0.0
        rec = {
            "market": parts[0],
            "name": parts[1],
            "code": parts[2],
            "price": parts[3],
            "prev_close": parts[4],
            "open": parts[5],
            "volume_hand": parts[6],
            "turnover": parts[37] if len(parts) > 37 else "?",
            "high": parts[33] if len(parts) > 33 else "?",
            "low": parts[34] if len(parts) > 34 else "?",
            "change": parts[31] if len(parts) > 31 else "?",
            "change_pct": change_pct,
            "date_time": parts[30] if len(parts) > 30 else "?",
        }
        if len(parts) > 39:
            rec["pe"] = parts[39].strip() if parts[39].strip() else "?"
        if len(parts) > 44:
            rec["market_cap"] = parts[44].strip()
        if len(parts) > 45:
            rec["circulating_cap"] = parts[45].strip()
        if len(parts) > 38:
            rec["amplitude"] = parts[38].strip()
        results.append(rec)
    return results


# ──────────── 腾讯 K-Line API ────────────


def _kline_fetch(code: str, days: int = 365) -> Optional[list]:
    """获取 K-line 历史数据"""
    suffix = "sh" if str(code).startswith(("6", "9")) else "sz"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={suffix}{code},day,,,{days},qfq"
    cmd = [
        "curl", "-s", "--connect-timeout", "5", "--max-time", "10", url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=15)
        if r.returncode != 0 or not r.stdout:
            return None
        data = json.loads(r.stdout.decode("utf-8"))
        qfq = data.get("data", {}).get(f"{suffix}{code}", {}).get("qfqday", [])
        return [
            {
                "date": row[0],
                "close": float(row[1]),
                "open": float(row[2]) if len(row) > 2 else None,
                "high": float(row[3]) if len(row) > 3 else None,
                "low": float(row[4]) if len(row) > 4 else None,
                "volume": int(float(row[5])) if len(row) > 5 else None,
            }
            for row in qfq
        ]
    except Exception:
        return None


# ──────────── 核心查询函数 ────────────
# 所有 cache_get → cache_set 都用 akdb，优先读缓存


def _format_realtime(results: list) -> str:
    """格式化实时行情为文本"""
    out = []
    for r in results:
        name = r.get("name", "?")
        code = r.get("code", "?")
        price = r.get("price", "?")
        pct = r.get("change_pct", 0)
        pe = r.get("pe", "?")
        turnover = r.get("turnover", "?")
        mc = r.get("market_cap", "")
        pct_str = f"+{pct}%" if pct >= 0 else f"{pct}%"
        extra = f" PE:{pe}" if pe and pe != "?" else ""
        extra += f" 市值:{mc}亿" if mc and mc != "?" else ""
        extra += f" 成交:{turnover}" if turnover and turnover != "?" else ""
        out.append(f"{name}({code}) {price} {pct_str}{extra}")
    return "\n".join(out)


def stock_realtime(codes: list[str] = None, fmt: str = "text") -> None:
    """实时行情 — 读缓存 → 腾讯 GT API"""
    cat = "realtime"
    cache_key_parts = ["_".join(codes)] if codes else ["major"]

    cached = akdb.cache_get(cat, *cache_key_parts)
    if cached:
        if fmt == "json":
            output(cached, "json")
        else:
            print(_format_realtime(cached))
        return

    if codes:
        gt_codes = []
        for c in codes:
            c = c.strip()
            gt_codes.append(f"sh{c}" if c.startswith(("6", "9")) else f"sz{c}")
        results = _gt_fetch(*gt_codes)
    else:
        results = _gt_fetch(
            "sh000001", "sz399001", "sz399006",
            "sh000688", "sh000300", "sh000016", "sh000905",
        )

    if not results:
        output("暂无数据（API连接失败）", fmt)
        return

    akdb.cache_set(cat, results, *cache_key_parts, ttl=akdb.TTL["index"])

    if fmt == "json":
        output(results, "json")
    else:
        print(_format_realtime(results))


def stock_history(
    code: str, start: str = None, end: str = None, fmt: str = "text",
) -> None:
    """历史K线 — 读缓存 → 腾讯 K-Line API"""
    if not end:
        end = date.today().isoformat()
    if not start:
        start = (date.today() - timedelta(days=365)).isoformat()

    cat = "history"
    parts = [code, start, end]
    cached = akdb.cache_get(cat, *parts)
    if cached:
        output(cached, fmt)
        return

    results = _kline_fetch(code, days=365)
    if not results:
        output("历史数据获取失败", fmt)
        return

    start_d = datetime.strptime(start, "%Y-%m-%d").date()
    end_d = datetime.strptime(end, "%Y-%m-%d").date()
    filtered = [
        r for r in results
        if start_d <= datetime.strptime(r["date"], "%Y-%m-%d").date() <= end_d
    ]
    if not filtered:
        output("指定范围内无数据", fmt)
        return

    akdb.cache_set(cat, filtered, *parts)

    if fmt == "json":
        output(filtered, "json")
    else:
        out = []
        for r in filtered:
            out.append(
                f"{r['date']} "
                f"开:{r['open']} 收:{r['close']} "
                f"高:{r['high']} 低:{r['low']} "
                f"量:{r['volume']}"
            )
        output("\n".join(out))


def stock_info(code: str, fmt: str = "text") -> None:
    """个股基本信息 — 读缓存 → 腾讯 GT API + AKShare"""
    cat = "info"
    cached = akdb.cache_get(cat, code)
    if cached:
        output(cached, fmt)
        return

    prefix = "sh" if str(code).startswith(("6", "9")) else "sz"
    gt = _gt_fetch(f"{prefix}{code}")

    info = {}
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

    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=code)
        if df is not None and not df.empty:
            extra = dict(zip(df["item"], df["value"]))
            info.update(extra)
    except Exception:
        pass

    akdb.cache_set(cat, info, code)

    if fmt == "json":
        output(info, "json")
    else:
        for k, v in info.items():
            print(f"{k}: {v}")


def stock_financial(code: str, fmt: str = "text") -> None:
    """财务数据 — 读缓存 → AKShare"""
    cat = "finance"
    cached = akdb.cache_get(cat, code)
    if cached:
        output(cached, fmt)
        return

    try:
        import akshare as ak
        df = ak.stock_financial_abstract(symbol=code)
        if df is None or df.empty:
            output("财务数据获取失败", fmt)
            return

        date_cols = [c for c in df.columns if c not in ["选项", "指标"]][:2]
        latest = date_cols[0]
        prev = date_cols[1] if len(date_cols) > 1 else None

        metrics_data = {"periods": date_cols, "metrics": {}}
        for _, r in df[df["选项"] == "常用指标"].iterrows():
            name = r["指标"]
            metrics_data["metrics"][name] = {c: r[c] for c in date_cols}

        akdb.cache_set(cat, metrics_data, code, ttl=akdb.TTL["finance"])

        if fmt == "json":
            output(metrics_data, "json")
        else:
            print(f"=== {code} 财务数据 ===")
            print(f"报告期: {latest} | 上期: {prev or 'N/A'}\n")
            for _, r in df[df["选项"] == "常用指标"].iterrows():
                name = r["指标"]
                val_latest = r.get(latest, "?")
                val_prev = r.get(prev, "?") if prev else ""
                for key in [val_latest, val_prev]:
                    try:
                        v = float(key)
                        if abs(v) > 1e8:
                            key_new = f"{v/1e8:.2f}亿"
                        elif abs(v) > 1e4:
                            key_new = f"{v/1e4:.2f}万"
                        else:
                            key_new = f"{v:.2f}"
                        if key == val_latest:
                            val_latest_str = key_new
                        if key == val_prev:
                            val_prev_str = key_new
                    except (ValueError, TypeError):
                        pass
                if prev:
                    print(f"  {name}: {val_latest} (上期: {val_prev})")
                else:
                    print(f"  {name}: {val_latest}")
    except Exception as e:
        output(f"ERROR获取财务数据: {e}", fmt)


def _format_north(records: list) -> str:
    """格式化北向资金为文本"""
    out = []
    for r in records[:10]:
        dt = r.get("日期", "?")
        sh = r.get("沪股通-净流入", r.get("沪股通净流入", "?"))
        sz = r.get("深股通-净流入", r.get("深股通净流入", "?"))
        out.append(f"{dt} 沪股通:{sh} 深股通:{sz}")
    return "\n".join(out)


def north_flow(fmt: str = "text") -> None:
    """北向资金 — 读缓存 → AKShare"""
    cat = "north"
    cached = akdb.cache_get(cat, "all")
    if cached:
        if fmt == "json":
            output(cached, "json")
        else:
            print(_format_north(cached))
        return

    try:
        import akshare as ak
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is not None and not df.empty:
            records = df.to_dict(orient="records")
            akdb.cache_set(cat, records, "all")
            if fmt == "json":
                output(records, "json")
            else:
                print(_format_north(records))
            return
    except Exception:
        pass
    output("北向资金数据获取失败", fmt)


def _find_sector(code: str) -> str:
    """从 sector_map.json 查找股票所属行业"""
    import json
    map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sector_map.json")
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            sector_map = json.load(f)
        for sector, stocks in sector_map.items():
            if sector.startswith("_"):
                continue
            if code in stocks:
                return sector
    except Exception:
        pass
    return None


def peer_compare(code: str, fmt: str = "text") -> None:
    """同行业对比 — 基于本地行业映射 + Tencent GT API"""
    sector = _find_sector(code)
    if not sector:
        output(f"未找到 {code} 的行业归属信息", fmt)
        return

    map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sector_map.json")
    with open(map_path, "r", encoding="utf-8") as f:
        sector_map = json.load(f)
    peers = sector_map[sector]

    # Query all peers via GT API
    gt_codes = [_gt_code(c) for c in peers.keys()]
    results = _gt_fetch(*gt_codes)

    if not results:
        output(f"同行业数据获取失败（{sector}）", fmt)
        return

    # Sort by change_pct descending
    results.sort(key=lambda r: float(r.get("change_pct", 0)), reverse=True)
    my_idx = -1
    for i, r in enumerate(results):
        if r["code"] == code:
            my_idx = i
            break

    if fmt == "json":
        output({
            "sector": sector,
            "your_position": my_idx,
            "peers": results,
            "count": len(results),
        }, "json")
        return

    # Text output
    out = [f"\n【{sector}】同行业对比（{len(results)}只）\n"]
    out.append(f"{'名称':<10} {'代码':<8} {'现价':<8} {'涨跌幅':<8} {'PE':<8} {'市值(亿)':<10}")
    out.append("-" * 55)
    for r in results:
        name = r.get("name", "?")
        code_s = r.get("code", "?")
        price = r.get("price", "?")
        pct = r.get("change_pct", 0)
        pct_str = f"+{pct}%" if float(pct) >= 0 else f"{pct}%"
        pe = r.get("pe", "?")
        mc = r.get("market_cap", "?")
        marker = " <<<" if r["code"] == code else ""
        out.append(f"{name:<10} {code_s:<8} {price:<8} {pct_str:<8} {pe:<8} {mc:<10}{marker}")
    out.append(f"\n你在本行业中排名第 {my_idx + 1} / {len(results)}")
    output("\n".join(out), fmt)


def index_spot(fmt: str = "text") -> None:
    """主要指数行情"""
    stock_realtime(None, fmt)


def macro_data(indicator: str = "shibor", fmt: str = "text") -> None:
    """宏观经济指标 — AKShare"""
    cat = "macro"
    cached = akdb.cache_get(cat, indicator)
    if cached:
        output(cached, fmt)
        return

    import akshare as ak
    mapping = {
        "shibor": ("Shibor 利率", "rate_interbank"),
        "cpi": ("CPI 数据", "macro_china_cpi_monthly"),
        "pmi": ("PMI 数据", "macro_china_pmi"),
        "gdp": ("GDP 数据", "macro_china_gdp"),
    }
    if indicator not in mapping:
        output(f"支持的指标: {', '.join(mapping.keys())}", fmt)
        return
    name, func_name = mapping[indicator]
    try:
        df = getattr(ak, func_name)()
        if fmt == "json":
            records = df.to_dict(orient="records")
            akdb.cache_set(cat, records, indicator)
            output(records, "json")
        else:
            output(f"=== {name} ===\n{df.head(20).to_string(index=False)}")
    except Exception as e:
        output(f"ERROR获取{name}: {e}", fmt)


def stock_notice(security: str, days: int = 30, fmt: str = "text") -> None:
    """公司公告 — AKShare"""
    from datetime import datetime, timedelta
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    try:
        import akshare as ak
        df = ak.stock_individual_notice_report(security=security, begin_date=start_date, end_date=end_date)
        if df is None or df.empty:
            output(f"{security} 近{days}天无公告", fmt)
            return
        if fmt == "json":
            output(df.to_dict(orient="records"), "json")
        else:
            print(f"=== {security} 公告（{start_date}~{end_date}）===")
            print(df[['公告日期','公告标题','公告类型']].to_string(index=False))
    except Exception as e:
        output(f"ERROR获取公告: {e}", fmt)


def stock_shareholder(symbol: str, fmt: str = "text") -> None:
    """股东人数变化 — AKShare (ths)"""
    try:
        import akshare as ak
        df = ak.stock_shareholder_change_ths(symbol=symbol)
        if df is None or df.empty:
            # 尝试另一个接口
            try:
                df = ak.stock_circulate_stock_holder(symbol=symbol)
            except Exception:
                pass
        if df is None or df.empty:
            output(f"{symbol} 股东数据获取失败或为空", fmt)
            return
        if fmt == "json":
            output(df.to_dict(orient="records"), "json")
        else:
            print(f"=== {symbol} 股东信息 ===")
            print(df.head(10).to_string(index=False))
    except Exception as e:
        output(f"ERROR获取股东数据: {e}", fmt)


def stock_research(symbol: str, fmt: str = "text") -> None:
    """研报/调研 — AKShare"""
    try:
        import akshare as ak
        df = ak.stock_research_report_em(symbol=symbol)
        if df is None or df.empty:
            output(f"{symbol} 研报数据获取失败", fmt)
            return
        if fmt == "json":
            output(df.to_dict(orient="records"), "json")
        else:
            print(f"=== {symbol} 研报/调研 ===")
            cols = [c for c in ['发布日期','标题','机构','评级','行业'] if c in df.columns]
            print(df[cols].head(10).to_string(index=False) if cols else df.head(10).to_string(index=False))
    except Exception as e:
        output(f"ERROR获取研报: {e}", fmt)


def commodity_price(indicator: str = "index", fmt: str = "text") -> None:
    """大宗商品价格指数 — AKShare"""
    try:
        import akshare as ak
        if indicator == "index":
            df = ak.macro_china_commodity_price_index()
        else:
            df = ak.futures_spot_price(date=indicator)
        if df is None or df.empty:
            output(f"商品价格数据获取失败", fmt)
            return
        if fmt == "json":
            output(df.to_dict(orient="records"), "json")
        else:
            print(f"=== 大宗商品价格 ===")
            print(df.head(15).to_string(index=False))
    except Exception as e:
        output(f"ERROR获取商品价格: {e}", fmt)


def show_cache(fmt: str = "text") -> None:
    """查看缓存状态"""
    stats = akdb.cache_stats()
    print(f"数据库: {stats['db_path']}")
    print(f"缓存总数: {stats['total']} (有效 {stats['valid']} / 过期 {stats['expired']})")
    print(f"快照数: {stats['snapshots']}")


def clear_cache() -> None:
    count = akdb.cache_clear_all()
    print(f"已清空 {count} 条缓存")


# ──────────── CLI ────────────


def sector_rank(fmt: str = "text") -> None:
    """行业板块涨跌幅排名 — 同花顺THS行业指数"""
    try:
        import akshare as ak
    except ImportError:
        output("akshare 未安装", fmt)
        return

    try:
        df = ak.stock_board_industry_summary_ths()
        if df is None or df.empty:
            output("THS行业数据获取失败: 返回空", fmt)
            return

        # 标准化列名
        col_map = {"板块": "名称", "涨跌幅": "涨跌幅"}
        df.rename(columns=col_map, inplace=True)

        if "涨跌幅" in df.columns:
            df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce").fillna(0)
            df = df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)

        if fmt == "json":
            # 只保留主要字段
            cols = ["名称", "涨跌幅", "总成交量", "总成交额", "净流入", "上涨家数", "下跌家数", "领涨股"]
            cols = [c for c in cols if c in df.columns]
            output(df[cols].head(30).to_dict(orient="records"), "json")
            return

        out = [f"\n【行业板块涨跌幅排名】共{len(df)}个行业 数据源: 同花顺\n"]
        out.append(f"{'排名':<4} {'行业':<12} {'涨跌幅':<10} {'成交额(亿)':<12} {'净流入(亿)':<12} {'上涨':<6} {'下跌':<6} {'领涨股':<10}")
        out.append("-" * 80)

        for i, (_, row) in enumerate(df.iterrows(), 1):
            pct = row.get("涨跌幅", 0)
            pct_str = f"+{pct:.2f}%" if float(pct) >= 0 else f"{pct:.2f}%"
            amt = row.get("总成交额", "-")
            amt_str = f"{float(amt):,.1f}" if isinstance(amt, (int, float)) else str(amt)
            flow = row.get("净流入", "-")
            flow_str = f"+{float(flow):,.1f}" if isinstance(flow, (int, float)) and float(flow) >= 0 else f"{float(flow):,.1f}" if isinstance(flow, (int, float)) else str(flow)
            up = row.get("上涨家数", "-")
            down = row.get("下跌家数", "-")
            leader = row.get("领涨股", "")
            leader_str = leader if leader and leader != "nan" else "-"
            out.append(f"{i:<4} {row['名称']:<12} {pct_str:<10} {amt_str:<12} {flow_str:<12} {up:<6} {down:<6} {leader_str:<10}")

            # 只显示前30
            if i >= 30:
                out.append(f"\n... 剩余{len(df)-30}个行业略 ...")
                break

        # 汇总
        avg = df["涨跌幅"].mean()
        top3 = df.head(3)["名称"].tolist()
        bot3 = df.tail(3)["名称"].tolist()
        out.append(f"\n行业平均涨跌幅: {avg:+.2f}%")
        out.append(f"领涨前三: {'、'.join(top3)}")
        out.append(f"领跌前三: {'、'.join(bot3)}")

        output("\n".join(out), fmt)

    except Exception as e:
        output(f"THS行业数据获取失败: {e}", fmt)


def main():
    parser = argparse.ArgumentParser(
        description="AKShare 数据查询工具 — 投资委员会数据基础设施",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s realtime                  # 主要指数
  %(prog)s realtime 600519           # 指定个股
  %(prog)s realtime 600519 000858    # 多只
  %(prog)s history 600519            # 近一年日K
  %(prog)s history 600519 --start 2026-01-01 --end 2026-05-09
  %(prog)s finance 600519            # 财务数据
  %(prog)s info 600519               # 基本信息
  %(prog)s north                      # 北向资金
  %(prog)s index                      # 主要指数
  %(prog)s macro cpi                  # CPI
  %(prog)s peer_compare 601138        # 同行业对比
  %(prog)s sector                      # 行业板块涨跌幅排名
  %(prog)s sector --fmt json          # 行业排名(JSON格式)
  %(prog)s cache                      # 查看缓存状态
  %(prog)s notice 002395              # 公司公告（近30天）
  %(prog)s notice 002395 --fmt json   # 公告JSON输出
  %(prog)s shareholder 002395         # 股东人数变化
  %(prog)s research 002395            # 研报/调研
  %(prog)s commodity                  # 大宗商品价格指数
  %(prog)s --clear-cache              # 清空缓存
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="realtime",
        choices=["realtime", "history", "finance", "info", "north", "index", "macro", "cache", "peer_compare", "sector", "notice", "shareholder", "research", "commodity"],
        help="查询类型",
    )
    parser.add_argument("codes", nargs="*", default=None, help="股票代码")
    parser.add_argument("--start", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="截止日期 YYYY-MM-DD")
    parser.add_argument("--fmt", default="text", choices=["text", "json"], help="输出格式")
    parser.add_argument("--clear-cache", action="store_true", help="清空全部缓存")

    args = parser.parse_args()

    if args.clear_cache:
        clear_cache()
        return

    if args.command == "cache":
        show_cache(args.fmt)
        return

    if args.command in ("realtime", "index"):
        stock_realtime(args.codes or None, args.fmt)
        return

    if args.command == "history":
        if not args.codes:
            print("ERROR: history 需要股票代码，如 600519")
            sys.exit(1)
        stock_history(args.codes[0], args.start, args.end, args.fmt)
        return

    if args.command == "finance":
        if not args.codes:
            print("ERROR: finance 需要股票代码")
            sys.exit(1)
        stock_financial(args.codes[0], args.fmt)
        return

    if args.command == "info":
        if not args.codes:
            print("ERROR: info 需要股票代码")
            sys.exit(1)
        stock_info(args.codes[0], args.fmt)
        return

    if args.command == "north":
        north_flow(args.fmt)
        return

    if args.command == "macro":
        macro_data(args.codes[0] if args.codes else "shibor", args.fmt)
        return

    if args.command == "peer_compare":
        if not args.codes:
            print("ERROR: peer_compare 需要股票代码，如 601138")
            sys.exit(1)
        peer_compare(args.codes[0], args.fmt)
        return

    if args.command == "sector":
        sector_rank(args.fmt)
        return

    if args.command == "notice":
        if not args.codes:
            print("ERROR: notice 需要股票代码，如 002395")
            sys.exit(1)
        stock_notice(args.codes[0], fmt=args.fmt)
        return

    if args.command == "shareholder":
        if not args.codes:
            print("ERROR: shareholder 需要股票代码")
            sys.exit(1)
        stock_shareholder(args.codes[0], args.fmt)
        return

    if args.command == "research":
        if not args.codes:
            print("ERROR: research 需要股票代码")
            sys.exit(1)
        stock_research(args.codes[0], args.fmt)
        return

    if args.command == "commodity":
        commodity_price(args.codes[0] if args.codes else "index", args.fmt)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
