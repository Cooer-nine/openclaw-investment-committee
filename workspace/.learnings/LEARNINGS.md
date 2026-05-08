# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## 2026-05-07: 数据获取纪律 — web_fetch 失败时不得使用过时内部知识

**类别**: correction | best_practice

**背景**: 青龙委员在准备1万元建仓方案时，`web_fetch` 返回 error，他直接使用了内部知识库中的陈旧价格（512690酒ETF误判为0.96-1.03，实际约0.478），导致方案需要勘误。

**改正**:
1. `web_fetch` 返回 error → 立即调用 `smart-web-fetch` skill（SearXNG）重试
2. `smart-web-fetch` 也失败 → 如实告知用户，绝不编造数据
3. 已写入 MEMORY.md 作为永久规范

**关键认识**: 对于投资业务，数据准确性与实时性比任何知识库都重要。没有准确数据时，"我不知道"是比"我编一个"更好的回答。
