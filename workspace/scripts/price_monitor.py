#!/usr/bin/env python3
"""
股票价格监控脚本 — 参数化版本
数据源：腾讯 GT API（毫秒级，单股查询）
触发方式：通过 OpenClaw Hook 推送提醒到飞书群

用法：
  # 启动监控
  python3 price_monitor.py start --code 600406 --name 国电南瑞 --target 25.00 --direction below --repeat yes

  # 列出活跃监控
  python3 price_monitor.py list

  # 停止某只监控
  python3 price_monitor.py stop --code 600406

  # 停止全部
  python3 price_monitor.py stop-all
"""

import re
import os
import sys
import json
import time
import signal
import logging
import argparse
import requests
from datetime import datetime, time as dt_time

# ========== 全局配置（通常不需要改）==========
OPENCLAW_HOOK_URL = "http://127.0.0.1:18180/hooks/agent"
OPENCLAW_HOOK_TOKEN = "154276839Ycz"

# 默认推送目标（飞书公司群）
DEFAULT_CHANNEL = "feishu"
DEFAULT_TARGET = "chat:oc_fc2feae46d030b6c73742bcbc4fe003d"

# 检查间隔（秒）
CHECK_INTERVAL = 10

# 仅交易时段运行
TRADING_HOURS_ONLY = True

# 脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(WORKSPACE_DIR, 'log')
DATA_DIR = os.path.join(WORKSPACE_DIR, 'data')
STATE_FILE = os.path.join(DATA_DIR, 'monitor_state.json')
# ==============================================


def setup_logger(code):
    """为每个监控实例创建独立日志"""
    logger = logging.getLogger(f'monitor_{code}')
    logger.setLevel(logging.INFO)

    # 确保日志目录存在
    os.makedirs(LOG_DIR, exist_ok=True)

    # 文件处理器
    fh = logging.FileHandler(os.path.join(LOG_DIR, f'monitor_{code}.log'))
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)

    # 控制台处理器（避免重复添加）
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(ch)

    return logger


def load_state():
    """加载所有监控状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception as e:
            print(f"加载状态文件失败: {e}")
    return {}


def save_state(state):
    """保存监控状态"""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"保存状态文件失败: {e}")


def detect_market(code):
    """根据股票代码前缀判断市场"""
    code = str(code)
    if code.startswith('6') or code.startswith('9'):
        return 'sh'
    elif code.startswith('0') or code.startswith('3') or code.startswith('2'):
        return 'sz'
    elif code.startswith('4') or code.startswith('8'):
        return 'bj'
    return 'sh'  # 默认


def get_stock_real_price(code, market=None):
    """通过腾讯 GT API 获取实时股价"""
    if market is None:
        market = detect_market(code)

    url = f"http://qt.gtimg.cn/q={market}{code}"
    try:
        resp = requests.get(url, timeout=5)
        resp.encoding = "gbk"
        text = resp.text.strip()

        match = re.search(r'"(.*?)"', text)
        if not match:
            return None

        fields = match.group(1).split("~")
        if len(fields) < 4:
            return None

        # 字段3=当前价，字段1=名称
        price_str = fields[3].strip()
        name = fields[1] if len(fields) > 1 else code
        if not price_str:
            return None, name
        return float(price_str), name

    except (requests.Timeout, requests.ConnectionError, ValueError, IndexError):
        return None, None


def is_trading_time():
    """判断是否在交易时段"""
    now = datetime.now()
    if now.weekday() >= 5:  # 周末
        return False

    t = now.time()
    morning_start = dt_time(9, 25)
    morning_end = dt_time(11, 30)
    afternoon_start = dt_time(13, 0)
    afternoon_end = dt_time(15, 0)

    return (morning_start <= t <= morning_end) or (afternoon_start <= t <= afternoon_end)


def push_alert(logger, config, price, name):
    """通过 OpenClaw Hook 推送提醒"""
    code = config['code']
    target_price = config['target_price']
    direction = config.get('direction', 'below')
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    direction_text = "跌破" if direction == 'below' else "涨至"
    emoji = "🔻" if direction == 'below' else "🚀"

    message = (
        f"{emoji} **股价提醒**\n"
        f"股票：{code}（{name}）\n"
        f"当前价：{price}\n"
        f"条件：{direction_text}目标价 {target_price}\n"
        f"时间：{now_str}\n\n"
        f"请评估是否操作。"
    )

    payload = {
        "message": message,
        "agentId": "main",
        "wakeMode": "now",
        "deliver": True,
        "channel": config.get('channel', DEFAULT_CHANNEL),
        "to": config.get('target', DEFAULT_TARGET),
        "name": f"股价提醒-{code}"
    }

    headers = {
        "Authorization": f"Bearer {OPENCLAW_HOOK_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(OPENCLAW_HOOK_URL, json=payload, headers=headers, timeout=10)
        logger.info(f"Hook 推送状态码: {resp.status_code}")
        logger.debug(f"Hook 推送响应: {resp.text[:200]}")
        if resp.status_code == 200:
            return True
        else:
            logger.error(f"推送失败 HTTP {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"推送请求失败: {e}")
        return False


def run_monitor(config):
    """运行单个监控实例（阻塞）"""
    code = config['code']
    name = config.get('name', code)
    target_price = config['target_price']
    direction = config.get('direction', 'below')
    repeat = config.get('repeat', 'yes')
    interval = config.get('interval', CHECK_INTERVAL)
    alert_once = config.get('trading_hours_only', TRADING_HOURS_ONLY)

    logger = setup_logger(code)
    market = detect_market(code)
    alerted = False
    running = True

    # 信号处理
    def handler(signum, frame):
        nonlocal running
        logger.info(f"收到信号 {signum}，准备退出...")
        running = False

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    logger.info(f"🚀 开始监控 {code}（{name}）")
    logger.info(f"   条件: 股价 {'≤' if direction == 'below' else '≥'} {target_price}")
    logger.info(f"   间隔: {interval}s | 重复提醒: {repeat}")
    logger.info(f"   交易时段运行: {alert_once}")
    logger.info(f"   推送至: {config.get('channel', DEFAULT_CHANNEL)} → {config.get('target', DEFAULT_TARGET)}")
    logger.info("=" * 50)

    while running:
        # 交易时段检查
        if alert_once and not is_trading_time():
            if alerted and repeat == 'yes':
                alerted = False
            # 非交易时段每30秒检查一次，减少日志输出
            time.sleep(30)
            continue

        price, real_name = get_stock_real_price(code, market)
        if price is None:
            logger.debug("获取价格失败，跳过")
            time.sleep(interval)
            continue

        name = real_name or name
        logger.info(f"[{code}] {name} 当前价: {price} | 目标: {target_price} | 已提醒: {alerted}")

        # 判断是否触发
        triggered = (direction == 'below' and price <= target_price) or \
                     (direction == 'above' and price >= target_price)

        if triggered:
            if not alerted:
                logger.warning(f"⚠️ 触发！当前价 {price} {'≤' if direction == 'below' else '≥'} 目标 {target_price}")
                if push_alert(logger, config, price, name):
                    alerted = True
                    # 更新状态文件
                    state = load_state()
                    state[code] = {
                        "name": name,
                        "target_price": target_price,
                        "direction": direction,
                        "alerted": True,
                        "triggered_at": datetime.now().isoformat(),
                        "trigger_price": price,
                        "repeat": repeat
                    }
                    save_state(state)

                    if repeat == 'no':
                        logger.info("单次提醒模式，退出")
                        break
            else:
                logger.debug("已触发过，跳过重复提醒")
        else:
            if alerted and repeat == 'yes':
                logger.info(f"价格{'回升' if direction == 'below' else '回落'}至目标价以上，重置提醒状态")
                alerted = False
                state = load_state()
                if code in state:
                    state[code]["alerted"] = False
                    save_state(state)

        # 分段 sleep
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    logger.info("监控已停止")


# ====== CLI 命令处理 ======

def cmd_start(args):
    """启动一个新的监控"""
    code = args.code
    name = args.name or code
    target = args.target
    direction = args.direction
    repeat = args.repeat

    # 校验参数
    if target <= 0:
        print("❌ 目标价必须大于0")
        return 1

    config = {
        "code": code,
        "name": name,
        "target_price": target,
        "direction": direction,
        "repeat": repeat,
        "channel": args.channel or DEFAULT_CHANNEL,
        "target": args.target_chat or DEFAULT_TARGET,
        "interval": args.interval or CHECK_INTERVAL,
        "trading_hours_only": args.trading_only
    }

    # 先验证数据源可用
    print(f"🔍 验证数据源: {code}...")
    price, real_name = get_stock_real_price(code)
    if price is None:
        print(f"❌ 无法获取 {code} 的行情数据，请检查股票代码")
        return 1
    print(f"✅ 当前价: {price} | 名称: {real_name}")
    config['name'] = real_name or name

    # 记录到状态文件
    state = load_state()
    state[code] = {
        "name": config['name'],
        "target_price": target,
        "direction": direction,
        "alerted": False,
        "repeat": repeat
    }
    save_state(state)

    print(f"✅ 监控配置已保存: {code}（{config['name']}）→ {'≤' if direction == 'below' else '≥'}{target}")
    print(f"   启动监控...")

    # Fork 子进程运行监控
    pid = os.fork()
    if pid == 0:
        # 子进程
        run_monitor(config)
        sys.exit(0)
    else:
        # 父进程
        print(f"   监控进程 PID: {pid}")
        # 保存 PID
        state = load_state()
        if code in state:
            state[code]["pid"] = pid
            save_state(state)
        print(f"   日志: tail -f {LOG_DIR}/monitor_{code}.log")
        print(f"   停止: python3 price_monitor.py stop --code {code}")
        return 0


def cmd_stop(args):
    """停止某只监控"""
    code = args.code
    state = load_state()

    if code not in state:
        print(f"❌ 未找到 {code} 的监控记录")
        return 1

    pid = state[code].get("pid")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"✅ 已发送停止信号给 {code} (PID {pid})")
        except ProcessLookupError:
            print(f"ℹ️ 进程 {pid} 已不存在")
        except Exception as e:
            print(f"⚠️ 停止失败: {e}")

    del state[code]
    save_state(state)
    print(f"✅ 监控 {code} 已移除")
    return 0


def cmd_stop_all(args):
    """停止所有监控"""
    state = load_state()
    count = 0
    for code, info in list(state.items()):
        pid = info.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                count += 1
            except:
                pass
    save_state({})
    print(f"✅ 已停止 {count} 个监控进程，清空状态")
    return 0


def cmd_list(args):
    """列出所有活跃监控"""
    state = load_state()
    if not state:
        print("📭 暂无活跃监控")
        return 0

    print(f"{'代码':<10} {'名称':<12} {'目标价':<10} {'方向':<8} {'状态':<10} {'PID':<8}")
    print("-" * 60)
    for code, info in sorted(state.items()):
        name = info.get('name', '')
        target = info.get('target_price', '')
        direction = '≤' if info.get('direction') == 'below' else '≥'
        status = '🟢 已触发' if info.get('alerted') else '🔵 监控中'
        pid = info.get('pid', '-')
        print(f"{code:<10} {name:<12} {str(target):<10} {direction:<8} {status:<10} {str(pid):<8}")

    print("-" * 60)
    print(f"总计: {len(state)} 个监控")
    return 0


def main():
    parser = argparse.ArgumentParser(description="股票价格监控器")
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # start 命令
    start_parser = subparsers.add_parser('start', help='启动新监控')
    start_parser.add_argument('--code', required=True, help='股票代码，如 600406')
    start_parser.add_argument('--name', help='股票名称（可选，自动获取）')
    start_parser.add_argument('--target', required=True, type=float, help='目标价')
    start_parser.add_argument('--direction', choices=['below', 'above'], default='below',
                              help='触发方向：below=跌破触发，above=涨至触发')
    start_parser.add_argument('--repeat', choices=['yes', 'no'], default='yes',
                              help='是否重复提醒（no=触发一次后退出）')
    start_parser.add_argument('--channel', default=DEFAULT_CHANNEL, help='推送渠道')
    start_parser.add_argument('--target-chat', default=DEFAULT_TARGET, help='推送目标')
    start_parser.add_argument('--interval', type=int, default=CHECK_INTERVAL, help='检查间隔（秒）')
    start_parser.add_argument('--trading-only', action='store_true', default=True,
                              help='仅交易时段运行')

    # stop 命令
    stop_parser = subparsers.add_parser('stop', help='停止监控')
    stop_parser.add_argument('--code', required=True, help='股票代码')

    # stop-all 命令
    subparsers.add_parser('stop-all', help='停止所有监控')

    # list 命令
    subparsers.add_parser('list', help='列出所有监控')

    args = parser.parse_args()

    if args.command == 'start':
        return cmd_start(args)
    elif args.command == 'stop':
        return cmd_stop(args)
    elif args.command == 'stop-all':
        return cmd_stop_all(args)
    elif args.command == 'list':
        return cmd_list(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
