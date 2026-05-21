# OpenClaw AI 投资委员会 — 玄武

**🐢 玄武** — AI 投资委员会主席，20年投资经验（模拟），统筹委员做出资产配置决策。

## 系统架构

```
~/.openclaw/
├── openclaw.json                     ← 生产配置（已 gitignore，不提交）
├── openclaw.json.template            ← 脱敏配置模板
├── README.md                         ← 本文件
├── .gitignore
│
├── workspace/                        ← 玄武（主席、投资委员会大脑）
│   ├── AGENTS.md / SOUL.md           全局行为准则、决策铁律
│   ├── MEMORY.md                     长期记忆、持仓索引、客户路由表
│   ├── scripts/                      数据脚本（akshare、价格监控）
│   │   ├── akshare_data.py           AKShare 行情查询入口
│   │   ├── akdb.py                   SQLite 缓存层
│   │   ├── akcron.py                 定时预取脚本
│   │   └── price_monitor.py          股价实时监控（腾讯GT API + hooks推送）
│   ├── skills/                       安装的技能
│   │   └── stock-monitor/            价格监控 Skill（触发条件由用户设定）
│   ├── 策略/                         策略文档
│   │   └── 模拟盘1号-两周策略.md      模拟盘策略
│   ├── PLANS/                        系统发展计划
│   └── log/ / data/                  运行产物（已 gitignore）
│
├── workspace-qinglong/               ← 青龙（保守派委员）
├── workspace-zhuque/                 ← 朱雀（成长派委员）
├── workspace-baihu/                  ← 白虎（激进派委员）
├── workspace-Orobas/                 ← Orobas（数据查询 Agent）
├── workspace-collector/              ← 收藏家（司库，持仓与交易管理）
│
└── skills/ (plugin-skills/)          飞书/蓝信/其他插件技能
```

## 委员会构成

| Agent | 角色 | 模型 | 职责 |
|-------|------|------|------|
| 玄武（main） | 主席 | DeepSeek V4 Flash | 接收议题、召集委员、综合决策、推群 |
| 青龙（qinglong） | 保守派 | DeepSeek V4 Pro | 风控优先，技术分析+基本面 |
| 朱雀（zhuque） | 成长派 | Kimi K2.5 | 成长逻辑，产业趋势+题材驱动 |
| 白虎（baihu） | 激进派 | Qwen3.6+ | 弹性优先，事件驱动+主题博弈 |
| Orobas（orobas） | 数据查询 | GLM-4.7-Flash | AKShare/腾讯GT/Tushare 行情查询 |
| 收藏家（collector） | 司库 | DeepSeek V4 Flash | 持仓管理、交易流水、收盘汇总 |

## 核心能力

### 投资决策
1. 用户提出议题（"怎么看 XX 股票"、"要不要加仓"）
2. 玄武向 Orobas 查询基础数据 → 包装成议题
3. 并行召集三位委员 → 各自独立分析
4. 收集回复、识别共识与分歧
5. 综合评级，输出决策（固定格式：评级+意见+采纳/相悖观点+逻辑）
6. 推送到飞书群

### 数据查询
- **AKShare**：A 股/ETF/指数行情、北向资金、板块数据
- **腾讯 GT API**：毫秒级实时行情（价格监控用）
- **Tushare**：财务数据、股东变化、公告调研
- **SQLite 缓存**：6h 行情/7d 财务/1d 基本信息 TTL

### 定时任务
| 时间 | 任务 | 说明 |
|------|------|------|
| 09:00 交易日 | 盘前简报 | 热点新闻 + 公司ETF持仓回顾 → 公司群 |
| 09:25 交易日 | 开盘数据预取 | AKShare 开盘前跑一次 |
| 15:05 交易日 | 收盘数据 | AKShare 收盘后数据归档 |
| 15:10 交易日 | 收盘汇总 | 持仓浮动盈亏 + 推送到订阅群 |

### 股价监控（2026-05-20 新增）
- Python 脚本后台运行，通过腾讯 GT API 实时查询
- 触发条件由用户设定（跌破/涨至）
- 到达目标价后通过 OpenClaw Hooks → 飞书群推送
- 零消耗直到触发（无 LLM 调用）
- 支持多股同时监控，独立子进程

### 飞书多群推送
- 公司群：仅公司 ETF 持仓
- 客户群：仅该客户个人持仓
- 晨报/收盘报：按客户订阅推送，自动扣费（2元/次）

## 安全措施

| 措施 | 说明 |
|------|------|
| `openclaw.json` 已 gitignore | 生产配置含 API Key、飞书 Secret |
| `.env_tushare` 已 gitignore | Tushare API Token |
| Client 数据库已 gitignore | positions.db / transactions.db / clients.json |
| Runtime 产物已 gitignore | logs, caches, session data |
| hooks.token ≠ gateway.auth.token | OpenClaw 强制要求分离 |
| 数据按群隔离 | 公司群不推客户数据，客户群不推公司数据 |

## 部署

```bash
# 1. 复制配置模板
cp openclaw.json.template openclaw.json

# 2. 替换占位符（API Key、App Secret、Token 等）
# 3. 确保 conda env py39 存在（akshare 环境）
# 4. 启动
openclaw gateway start
```

## 注意事项

- **网关重启仅限玄武主席**
  - 其他 Agent 认为需要重启时 → 报告玄武评估
  - 玄武执行前确认所有通信已完成
- **不编造数据**：查询超时或失败时如实告知，不用旧数据凑答案
- **持仓数据不记 memory**：明细存 collector 数据库，MEMORY.md 仅保留决策摘要索引
