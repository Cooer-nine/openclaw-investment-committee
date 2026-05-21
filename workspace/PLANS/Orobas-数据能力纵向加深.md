# Orobas 数据能力纵向加深计划

**批准日期：** 2026-05-11
**状态：** 待执行（无依赖，可随时开始）

---

## 一、目的

在 Orobas 现有数据查询能力（实时行情、历史K线、财务数据、基本信息）基础上，沿"数据查询"主线做深，使委员分析时能从单一入口获取更全面的数据。

## 二、新增能力（按优先级排序）

### P0 — 行业板块涨跌幅排名

- **目标：** 返回板块名称、涨跌幅、领涨股等
- **查询方式：** `conda run -n py39 python scripts/akshare_data.py sector`

### P1 — 资金流向

- **目标：** 北向资金当日净流入/流出，个股主力/散户净流入
- **查询方式：** `conda run -n py39 python scripts/akshare_data.py north_flow [code]`

### P2 — 同行业对比

- **目标：** 输入一个股票代码，返回同板块对比列表（含市值、PE/PB 中位数）
- **查询方式：** `conda run -n py39 python scripts/akshare_data.py peer_compare <code>`

## 三、环境测试结果（2026-05-11）

已在阿里云服务器测试了各数据源的可用性：

| 数据源 | 可用？ | 说明 |
|--------|:-----:|------|
| Tencent GT API (qt.gtimg.cn) | ✅ | 个股实时行情稳定可靠 |
| Sina Finance (web_fetch) | ✅ | HTML 页面可读取，但核心数据区域为 JS 动态渲染 |
| AKShare (py39 conda) | ⚠️ | import 耗时 10s+，East Money API 连接被阻断 |
| East Money push2 API | ❌ | 请求直接被丢弃（连接超时或空响应） |
| Sina 板块排名页 | ❌ | 返回空内容（IP 被限） |

**核心限制：** 东方财富 (East Money) 的 AKShare 接口和 push2 API 从阿里云服务器被阻挡。Sina 板块排名页也返回空内容。

## 四、实施方案调整

由于 East Money / AKShare 方向受阻，P0/P1 改用**直连 Tencent GT API + 本地行业映射**方案：

### 方案：本地行业映射 + Tencent 实时报价

1. **行业映射数据**：从公开数据源（知乎/百度百科或现有前端数据）手工整理一批 A 股核心股票代码及其所属申万行业
2. **存储**：`data/sector_map.json`（静态映射，手动维护）或缓存在 SQLite 中
3. **查询逻辑**：
   - 用户请求 `sector` → 读取 sector_map.json → 获取该行业所有股票代码
   - 用 Tencent GT API 批量获取实时报价 → 加权计算行业涨跌幅
   - 按涨跌幅排序输出前十/所有行业
4. **优势**：不依赖任何可能被阻断的外部 API，完全自给

**备选方案（如果行业映射数据可以拿到）：**
- 同花顺/新浪的板块成分股数据（需测试各备选 URL）
- `web_fetch` 爬取同花顺公开板块页面

## 五、执行顺序与进度

### ✅ P2 — 同行业对比（已完成 2026-05-11）

- **行业映射表**：创建 `scripts/data/sector_map.json`，覆盖 20 个行业、~190 只标的
- **查询函数**：`peer_compare <code>` 已加入 akshare_data.py
- **数据源**：本地映射 + Tencent GT API 实时查询
- **输出**：同行业标的涨跌幅排名、PE、市值，标注查询标的所处位置
- **Orobas SOUL.md**：已更新可用命令表

### ✅ P0 — 行业板块涨跌幅排名（已完成 2026-05-14）

- **接口：** `ak.stock_board_industry_summary_ths()` — 同花顺THS行业实时指数
- **命令：** `python akshare_data.py sector`
- **输出：** 90个行业实时涨跌幅排名，含成交额、净流入、上涨/下跌家数、领涨股
- **数据源：** 同花顺（THS），从阿里云服务器可用
- **无需手工维护行业映射表** — 同花顺接口自动提供全行业数据

### 🔲 P1 — 资金流向（待实现）

东方财富 API 被服务器 IP 阻挡。替代方案：Tushare Pro（独立平台，免费注册）。

**前置条件：** 已注册 tushare.pro，token 已配置。但当前为免费版（123分），权限仅限基础数据查询。
- ✅ Token 已就位
- ❌ 资金流向接口需要 2000 分（下一级需年费）→ 当前放弃
- ❌ 行业板块接口需要更高积分 → 当前放弃
- ✅ 可用接口：日线行情、基础财务指标等（消耗积分较少）

### 🔲 Tushare 板块数据（可替代 sector_map.json）

Tushare 提供标准申万行业分类和板块成分股API，但下一级需年费。当前放弃。

**替代方案：** 维持本地 sector_map.json + Tencent GT API。
