# 司库 Agent 开发计划

**批准日期：** 2026-05-11
**状态：** 待启动（等待董事会创建司库 Agent）

---

## 一、需求背景

为使用本系统的客户提供个人粒度的股票管理服务，包括：
- 客户持仓记录与管理（台账）
- 持仓表现跟踪与汇总
- 客户自定义模型匹配与个性化建议
- 阈值触发告警

## 二、架构设计

### 核心原则：Phase 1 即分家

**Orobas 与司库职责一刀切，从零开始就分清楚，不兼任、不分家。**

| Agent | 职责 | 数据归属 |
|-------|------|---------|
| **Orobas** | 行情查询、财报数据、宏观数据（被动响应） | `scripts/.akcache/akshare_cache.db` |
| **司库** | 客户持仓管理、交易记录、告警监控（可含主动行为） | `data/` 目录下独立 SQLite |

### 2.1 Agent 定位

- **名称：** 司库（或「会计」，待确定）
- **角色：** 后台 Agent，不直接接入飞书群
- **创建时机：** Phase 1 开始时即创建，不作为 Orobas 的附加职能
- **通信：** 通过 `sessions_send` 与玄武主席通信
- **数据：** 读写本地 SQLite，向 Orobas 查询实时行情

### 2.2 通信链路

```
飞书群（客户报单）
     │  message 接收
     ▼
玄武（主席）——统一对外出口
     │  sessions_send
     ▼
司库（后台 Agent）——客户持仓数据
     │  sessions_send("agent:orobas:main")
     ▼
Orobas（数据查询 Agent）——实时行情/财务数据
```

### 2.3 数据文件归属

- 市场数据：`scripts/.akcache/akshare_cache.db` → **Orobas 专属**
- 客户数据：`data/positions.db`, `data/transactions.db` → **司库专属**
- 两个 Agent 通过 `sessions_send` 通信，不共享文件写入权限

### 2.3 推送机制（方案 A+C 混用）

| 场景 | 方式 | 说明 |
|------|------|------|
| 每日收盘汇总 | 方案A | 司库完成 → sessions_send 通知玄武 → 玄武自动 message 推群 |
| 止损/止盈触发 | 方案C | 司库完成 → sessions_send 通知玄武 → 玄武审核后决定是否推群 |
| 客户查询持仓 | N/A | 客户在群内问 → 玄武转发司库查询 → 回复到群 |

## 三、数据存储

### 3.1 存储位置

```
/home/admin/.openclaw/workspace/data/
├── clients.json        # 客户信息（轻量，KV格式）
├── positions.db        # 持仓表（SQLite）
├── transactions.db     # 交易流水表（SQLite）
├── alerts.db           # 告警日志（SQLite）
└── models/             # 客户量化模型（JSON文件）
    ├── 仇行.json
    └── 檀博.json
```

### 3.2 数据库设计（positions.db）

待司库创建后进一步细化。初步设想：

**positions 表**
- id, client_id, stock_code, stock_name
- quantity（持仓数量）, avg_cost（买入均价）
- stop_loss_pct（止损线%）, take_profit_pct（止盈线%）
- created_at, updated_at

**transactions 表**
- id, client_id, stock_code, direction（buy/sell）
- price, quantity, amount
- note, created_at

### 3.3 数据获取

- 实时行情 → sessions_send("agent:orobas:main", "请求") 
- 利用 Orobas 的 cache-first 机制，避免重复 API 调用
- 当日首次查询可能触发 Orobas 实时抓取，后续命中缓存

## 四、开发顺序

### Phase 1（等待董事会创建司库 Agent 后立即执行）

1. **建表** — 在司库 Agent 工作区创建 `data/positions.db`, `data/transactions.db`, `data/alerts.db`
2. **写数据模块** — 参考 `akdb.py` 的写法，封装增删改查（`siku_db.py`）
3. **通信链路验证** — 司库 `sessions_send` Orobas 查行情 → 写本地 → 回报告主席
4. **持仓 CRUD** — 接收客户报单的增删改查
5. **收盘汇总** — 15:05 触发：查持仓计算浮盈 → 推汇总到主席 → 主席 message 推飞书群

### Phase 2（稳定后逐步叠加）

1. watchlist 关注列表 + 止盈止损阈值检查（初版）
2. 阈值触发时告警，主席审核后决定是否推群
3. 客户持仓快捷查询命令（群内问

### Phase 2（随后）

1. 实现 watchlist 关注列表
2. 实现阈值检查（止损/止盈触发）
3. 触发后通知玄武审核推送

### Phase 3（远期）

1. models 目录 + 客户量化模型规则引擎
2. 个性化建议生成
3. 可视化展示（如需）

## 五、注意事项

- **司库不进飞书群**（飞书群聊最多 1 bot 限制）
- 所有群内消息出口统一经过玄武主席
- 收盘汇总自动推，止损止盈需主席审核后推
- **司库不与 Orobas 混用** — 各自独立 SOUL.md，独立工作区，互不包含
- **数据层隔离** — Orobas 不碰 `data/`，司库不碰 `.akcache/`
- 司库需要行情时 → `sessions_send("agent:orobas:main", ...)` 走标准数据查询
