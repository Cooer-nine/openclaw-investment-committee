# 股票价格实时监控 Skill

**当以下情况时使用此 Skill：**
- 用户提出"帮我监控XX股票，到XX元提醒我"
- 用户想设置股价预警/提醒
- 用户问能否在某个价位通知TA
- 用户需要查看当前有哪些监控在运行
- 用户想停止某个监控

## 监控流程

### 1. 询问触发条件

用户提出监控需求后，收集以下信息（缺什么问什么）：

| 参数 | 说明 | 示例 |
|------|------|------|
| 股票代码 | 6位数字代码 | 600406 |
| 触发方向 | 跌破触发 / 涨至触发 | below / above |
| 目标价格 | 具体数字 | 25.00 |
| 重复提醒 | 触发一次后是否可再次提醒 | yes（默认）/ no |
| 推送目标 | 默认推送给当前群，用户有特别指定才改 | 公司群（默认） |

### 2. 对话示例

```
用户：帮我监控国电南瑞，跌破25的时候提醒我
→ 查询该股当前价
→ "好的，确认一下监控条件：
   股票：国电南瑞（600406）
   条件：股价 ≤ 25.00 时推送提醒到本群
   重复提醒：是（跌破后回升再跌破可再次触发）
   当前价：26.51
   确认开始监控吗？"

用户确认后
→ 调用 start_monitoring 启动
→ "✅ 已开始监控国电南瑞（600406）
   目标价 25.00，跌破即提醒
   查看日志：tail -f log/monitor_600406.log
   如需停止：请说'停止监控国电南瑞'"
```

### 3. 启动监控

在确认用户同意后，通过 exec 运行：

```bash
conda run -n py39 python3 scripts/price_monitor.py start \
  --code {股票代码} \
  --target {目标价} \
  --direction {below|above} \
  --repeat {yes|no}
```

各参数说明：
- `--code`：股票代码（纯数字），自动判断上交所/深交所
- `--name`：股票名称（可选，自动获取）
- `--target`：目标价格
- `--direction`：`below`=跌破触发，`above`=涨至触发
- `--repeat`：`yes`=重复提醒（默认），`no`=触发一次后退出
- `--interval`：检查间隔秒数（默认10秒）
- `--trading-only`：仅交易时段运行（默认开启）

### 4. 查看监控

```bash
conda run -n py39 python3 scripts/price_monitor.py list
```

输出示例：
```
代码        名称          目标价      方向      状态         PID
600406     国电南瑞       25.00      ≤         🔵 监控中   12345
```

### 5. 停止监控

```bash
# 停止某只
conda run -n py39 python3 scripts/price_monitor.py stop --code 600406

# 停止全部
conda run -n py39 python3 scripts/price_monitor.py stop-all
```

### 6. 查看日志

```bash
tail -f log/monitor_{股票代码}.log
```

## 触发流程

当股价达到目标条件时：

1. 脚本通过 OpenClaw Hook 推送消息给 main Agent
2. Hook 的 delivery 机制自动将提醒推送到飞书群
3. 提醒内容包含：股票名称代码、当前价、目标价、触发时间

## 技术说明

- **数据源**：腾讯 GT API（`qt.gtimg.cn`），单股毫秒级查询，免费无限制
- **运行方式**：`os.fork()` 创建子进程后台运行，每个监控独立进程
- **状态持久化**：`data/monitor_state.json` 记录所有监控状态
- **日志**：`log/monitor_{code}.log` 独立日志文件
- **钩子机制**：通过 OpenClaw Hooks（`POST /hooks/agent`）推送到飞书群
- **资源消耗**：单进程约 5MB 内存，10 秒间隔几乎无 CPU 占用

## 错误处理

- 腾讯 API 超时或失败 → 自动跳过本轮，下一轮重试
- 进程被意外终止 → 状态文件保留，可通过 `list` 查看
- 连续多次失败 → 仅记录日志，不影响运行
