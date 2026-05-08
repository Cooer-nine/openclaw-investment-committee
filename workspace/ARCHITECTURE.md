# OpenClaw 投资委员会架构图

```mermaid
flowchart TB
    subgraph 董事会["🏛️ 董事会"]
        Board[("董事会成员")]
    end

    subgraph 主席["🐢 玄武 - 投资委员会主席"]
        XW[Xuanwu<br/>决策风格：风控优先<br/>模型：deepseek-v4-flash]
    end

    subgraph 委员["👥 投资委员会"]
        QL["🐉 青龙<br/>保守派 · 稳健型<br/>模型：deepseek-v4-pro"]
        ZQ["🦅 朱雀<br/>成长派 · 成长型<br/>模型：kimi-k2.5"]
        BH["🐅 白虎<br/>激进派 · 进取型<br/>模型：qwen3.6-plus"]
    end

    subgraph 功能Agent["⚙️ 功能型 Agent（建设中）"]
        DA["📊 数据查询 Agent<br/>定时充能 + 按需响应<br/>模型：qwen3-coder-plus(免费)"]
        PA["📋 持仓监控 Agent<br/>阈值预警<br/>模型：qwen3-coder-plus(免费)"]
    end

    subgraph 基础设施["🔧 基础设施"]
        AK["AKShare 数据源<br/>A股行情/财务/板块<br/>Python 3.9 + conda"]
        Cache["本地缓存<br/>SQLite/JSON<br/>T日内数据复用"]
        Cron["定时任务<br/>09:25 / 15:05<br/>零 Token 消耗"]
    end

    subgraph 外部["🌐 外部"]
        GH["GitHub<br/>openclaw-investment-committee<br/>配置版本管理"]
        FS["飞书<br/>群聊/私信通信"]
        AL["阿里云服务器<br/>Alibaba Cloud Linux 3"]
    end

    Board -->|下达指令| XW
    Board -->|审批决策| XW
    XW -->|召集委员分析| QL
    XW -->|召集委员分析| ZQ
    XW -->|召集委员分析| BH
    QL -->|输出分析意见| XW
    ZQ -->|输出分析意见| XW
    BH -->|输出分析意见| XW
    XW -->|汇报决策| Board

    DA -->|查询| AK
    DA -->|读写| Cache
    DA -.->|响应查询| XW
    DA -.->|响应查询| QL
    DA -.->|响应查询| ZQ
    DA -.->|响应查询| BH

    PA -->|读取缓存| Cache
    PA -.->|条件预警| Board

    Cron -->|触发定时| DA

    XW -.-> FS
    QL -.-> FS
    ZQ -.-> FS
    BH -.-> FS

    subgraph 版本管理["📦 安全上传"]
        Config["openclaw.json.template<br/>脱敏配置模板"]
        WS["workspace/ 及 workspace-*/<br/>各 Agent 身份文件"]
        GitIgnore[".gitignore<br/>排除 credentials/ agents/ sessions"]
    end
    Config --> GH
    WS --> GH
    GitIgnore --> GH

    classDef board fill:#f9f,stroke:#333,stroke-width:2px
    classDef chairman fill:#e1f5fe,stroke:#0277bd,stroke-width:2px
    classDef member fill:#fff3e0,stroke:#e65100,stroke-width:1px
    classDef func fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,stroke-dasharray: 5 5
    classDef infra fill:#f3e5f5,stroke:#7b1fa2,stroke-width:1px
    classDef external fill:#eceff1,stroke:#546e7a,stroke-width:1px

    class Board board
    class XW chairman
    class QL,ZQ,BH member
    class DA,PA func
    class AK,Cache,Cron infra
    class GH,FS,AL external
```

---

## 完整架构说明

### 信息流

```
董事会 ──(议题)──→ 玄武 ──(委员召集)──→ 青龙 / 朱雀 / 白虎
                                    ↑                     │
                                    │      ┌──────────────┘
                                    │      ▼
                                    └──(分析意见)──
                                                  │
                                                  ▼
玄武 ──(综合决策)──→ 董事会
```

### 数据流

```
数据查询 Agent ←―(定时 09:25/15:05)― 定时任务
      │
      ├──(查数据)──→ AKShare ──→ 东方财富/新浪/同花顺
      │
      └──(写入/读取)──→ 本地缓存
              │
              ├──(读取)──→ 持仓监控 Agent
              │
              └──(读取)──→ 委员 Query

委员 Query 路径：
  委员提问 → 数据 Agent(qwen3-coder-plus)
           → 匹配脚本 → Python 脚本调 AKShare
           → 格式化输出 → 返回
```

### 关键设计决策

| 决策 | 理由 |
|---|---|
| 数据+监控 Agent 分离 | 职能不同，互不干扰 |
| 定时任务零 Token | Python 脚本直调 AKShare，不走模型 |
| miniconda 隔离 Python 3.9 | 不碰系统 Python 3.6，独立管理 |
| openclaw.json.template | 生产配置脱敏后上传 GitHub |
| 免费模型优先 | 数据 Agent 仅做匹配转发，几乎零推理 |

---

## 通信架构演进

```mermaid
flowchart LR
    subgraph 初始设想["**初始设想** 群聊互AT"]
        U1["董事会"]
        XW1["玄武"]
        QL1["青龙"]
        ZQ1["朱雀"]
        BH1["白虎"]
        G1["飞书群聊"]

        U1 -->|提问| G1
        XW1 -->|AT青龙| G1
        QL1 -->|AT朱雀| G1
        ZQ1 -->|AT白虎| G1
        BH1 -->|AT玄武| G1
    end

    subgraph 最终方案["**最终方案** 后台交互"]
        U2["董事会"]
        XW2["玄武"]
        QL2["青龙"]
        ZQ2["朱雀"]
        BH2["白虎"]
        G2["飞书群聊"]

        U2 -->|提问| G2
        G2 -->|结论汇报| U2
        XW2 ---|sessions_send| QL2
        XW2 ---|sessions_send| ZQ2
        XW2 ---|sessions_send| BH2
        QL2 ---|sessions_send| XW2
        ZQ2 ---|sessions_send| XW2
        BH2 ---|sessions_send| XW2
    end

    初始设想 -->|演进| 最终方案
```

| 对比维度 | 初始设想（群聊互@） | 最终方案（后台通信） |
|---|---|---|
| 群聊成员 | 4 个机器人 + 董事会 | 仅 1 个机器人（玄武）+ 董事会 |
| 委员讨论 | 群内 @ 对方，可见 | 后台 session_send，不可见 |
| 消息量 | 每条讨论都刷屏 | 只有提问和结论，干净 |
| 技术复杂度 | 需装社区插件、有信道冲突 | 零插件，OpenClaw 原生支持 |
| 可读性 | 消息爆炸，难以追踪 | 一条提问→一条结论，清晰 |

### 当前状态

- ✅ **已完成**：委员会主席（玄武）+ 三位委员（青龙/朱雀/白虎）
- ✅ **已完成**：GitHub 版本管理（脱敏模板 + 排除敏感文件）
- ✅ **已完成**：Python 3.9 + AKShare 基础设施
- 🔄 **待建设**：数据查询 Agent
- 🔄 **待建设**：持仓监控 Agent
