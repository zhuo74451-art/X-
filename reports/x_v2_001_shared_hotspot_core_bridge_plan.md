# X v2-001 Shared Hotspot Core Bridge Plan（不合并仓库）

目标：在不合并仓库、不复制文章项目代码的前提下，设计统一中间格式 `event_pack`，使 X 项目与文章项目未来可以共享“真实热点源→事实包→风控标记”的上游产物。

## 结论摘要

- 现在不合并仓库：两边处于不同阶段，且下游差异（X 多形态内容 vs 文章长文本）很大；直接合并会放大风险。
- 先统一 schema：用 `event_pack.jsonl` 作为跨仓交换的只读中间产物。
- X 项目继续保留现有 Hot Engine 队列（`out/hot_engine_queues/*.md` + `events.jsonl`），并在未来新增一个“导入共享 event_pack”的只读 adapter（第二阶段）。

## 共享边界（Core vs Adapter）

### Shared Hotspot Core（共享层应承担）

这些能力对文章与 X 都通用，应尽量只产出结构化中间物（不带平台风格）：

- 热点源接入（多源 ingestion）与 normalize（上游 item → 标准输入条目）
- 事件聚类（event cluster）
- 事实锚点组织：
  - `source_pack`：候选来源列表、来源层级、引用风险提示
  - `fact_pack`：confirmed/uncertain/should_not_claim
- 统一风控标记：`risk_flags`
- 推荐下游输出形态：`recommended_outputs`（只做“可做什么”，不做“怎么写”）

### X Adapter（X 专属层应承担）

这些能力强绑定 X 平台输出形态/策略，不进共享层：

- X 文案生成（official/personal/reply/quote/thread 等多形态）
- X 的 visual 路线（image_prompt 等）
- AI Reviewer / AI Risk Auditor / Hard Gate（X 发布前门禁）
- 发布（真实 publish 永远放在 adapter，且可被 gate 强制阻断）

## 统一 Event Pack Schema（跨仓中间格式）

共享层输出（event_pack）：

```json
{
  "event_id": "",
  "title": "",
  "summary": "",
  "event_type": "",
  "assets": [],
  "source_pack": [],
  "fact_pack": {
    "confirmed": [],
    "uncertain": [],
    "should_not_claim": []
  },
  "risk_flags": [],
  "image_candidates": [],
  "recommended_outputs": [
    "article",
    "x_post",
    "thread",
    "reply",
    "quote"
  ],
  "review_required": true
}
```

X Adapter 读取后输出（X 生成结构）：

```json
{
  "event_id": "",
  "official_post": "",
  "personal_post": "",
  "reply_angle": "",
  "quote_angle": "",
  "thread_outline": [],
  "image_prompt": "",
  "risk_flags": [],
  "ai_reviewer_required": true,
  "publish_status": "blocked_until_ai_review"
}
```

## 与当前 X Hot Engine 的对齐方式（映射）

当前 Hot Engine 已经输出一份接近 event_pack 的“事件评估行”（`events.jsonl`），建议新增一层“event_pack exporter”（未来做，不在本轮实现），将字段映射如下：

- `event_id` ← `event_cluster_id`
- `title` ← `cluster_title`
- `summary` ← `raw_summary`（或未来由 shared core 的 summarizer 产出）
- `event_type` ← 共享层分类器（X 仓库里已有雏形：`scripts/enrichment/event_type_classifier.py`，但未来应统一到共享层）
- `assets` ← 从文本抽取/或上游字段（当前 rulebook 里部分 whale digest 已做 asset/action 提取）
- `source_pack` ←
  - 最小版：`best_source_url` + `source_urls`
  - 完整版：由 source research / enrichment 产出并遵循 `configs/source_pack_schema.json`
- `fact_pack` ← `scripts/enrichment/fact_pack_builder.py`（未来对齐到共享层）
- `risk_flags` ← 从 `risk_level` + 规则命中原因 + 审核策略生成（共享层统一枚举）
- `recommended_outputs` ←
  - `whale_digest` 倾向 `thread/article`
  - 其它事件可默认 `x_post/thread/reply/quote`（仅推荐，不生成）
- `review_required` ← true（默认 true；当且仅当后续出现“强事实锚点 + 风险低 + 规则通过”才可允许自动降级）

## 数据源何时合并（merge timing）

### 现在不合并

原因：
- 文章项目正在准生产收尾；
- X 项目已有 Hot Engine 队列与规则体系；
- 直接合并仓库会增加发布/风控风险；
- 两边下游不同（文章 vs X）。

### 第一阶段：schema 对齐（推荐先做）

- X 项目：能导出/读取 `event_pack.jsonl`（不改变现有队列结构，属于兼容层）。
- 文章项目：导出 `event_pack.jsonl`（不改变其现有 pipeline）。
- 两个项目仍然分仓，各自独立运行。

### 第二阶段：只读桥接（X 侧新增只读 adapter）

在 X 项目新增（未来实现）：

- `adapters/import_shared_event_pack.py`
  - 只读读取共享目录或文章项目导出的 `event_pack.jsonl`
  - 输出到 X 的既有队列（或新增 `out/shared_event_pack_inbox/`）供后续生成/审核
  - 不改文章项目，不复制数据源逻辑

### 第三阶段：抽共享 Hotspot Core（稳定后再做）

当文章与 X 都稳定后，再考虑：
- 独立 `shared_hotspot_core` 包（或第三个仓库）
- 将真实热点源、清洗、聚类、source_pack/fact_pack、风险标记沉淀到共享层

## “什么时候合并数据源”（决策门槛）

只有同时满足以下条件，才进入第三阶段（抽共享 core）：

- 两边都稳定消费 `event_pack` ≥ 2 个迭代周期，字段不再频繁变动
- `fact_pack` 与 `risk_flags` 的枚举在两边一致（不再双份解释）
- X 的 AI Reviewer/Risk Auditor/Hard Gate 流程稳定，不会因上游波动导致误发布风险
- 文章项目的准生产指标稳定（可回滚、可观测）

在此之前，严格保持“分仓 + schema 统一 + 只读桥接”。
