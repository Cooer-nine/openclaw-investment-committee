# MEMORY.md — 青龙 🐉

## 案例教训（512690酒ETF价格误判）
- **错误：** 依赖内部知识估算512690约1.0元，实际约0.478元（偏差+109%）
- **根因：** `web_fetch` 失败后未启用备用数据源，直接用了过时知识库
- **正确做法：**
  - 东方财富基金API：`api.fund.eastmoney.com/f10/lsjz`（ETF净值）
  - 腾讯行情API：`qt.gtimg.cn/q=<code>`（实时股价）

## 规则四：数据查询统一出口（2026-05-07）
- **数据Agent：** 欧洛巴斯（Orobas/大眼，sessionKey=`agent:orobas:main`）
- 所有行情/财务/基本面/宏观数据查询必须通过 `sessions_send(agent:orobas:main)` 发起
- 禁止自行搜索或编造数据
- Orobas 无响应 → 上报主席玄武，不自行重试
- 直接数据源（Orobas不可达时备用）：东方财富基金API + 腾讯行情API
- **sessionKey 路由（2026-05-16）：** 公司群议题→`agent:orobas:main`；客户群议题→`agent:orobas:client-{客户名}`（如client-聪）。议题标签标明来源

## 个股深度分析补全规则（2026-05-18）
- 涉及个股分析时，除Orobas行情基础数据外，必须通过Orobas补充查询AKShare结构化数据：
  1. 公告 → `sessions_send(agent:orobas:main, "notice {代码}")`
  2. 股东人数/筹码 → `sessions_send(agent:orobas:main, "shareholder {代码}")`
  3. 研报/调研 → `sessions_send(agent:orobas:main, "research {代码}")`
  4. 商品/行业价格 → `sessions_send(agent:orobas:main, "commodity {品种}")`
- 数据优先级：行情基础 → AKShare补全 → 再出分析
- 案例教训：双象股份分析遗漏了25亿PMMA扩产公告、行业涨价、筹码集中等重要公开信息

## 规则五：禁止自行重启网关（2026-05-09）
- Agent 禁止执行 `gateway restart`，仅玄武主席有此权限
- 需重启时上报主席及原因
