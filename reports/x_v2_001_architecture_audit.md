# X v2-001 Architecture Audit（只读）

范围：仅审计 X 自动化仓库（本仓），不合并仓库、不改业务代码、不接真实发布、不调用付费模型。

项目根目录：`c:\Users\zhuo7\Desktop\X自动化\x_automation`

## 目录概览（与本次审计强相关）

- `scripts/`
  - `run_hot_engine_once.py`：Hot Engine 主入口（抓取→normalize→cluster→规则→队列落盘）。
  - `rules/`：聚类与规则评分（Rulebook / Queue Split）。
  - `adapters/import_integration_api.py`：Integration API 输入适配（热点源接入 + normalize）。
  - `generate_from_queue.py`：从队列调用 LLM 生成（本轮不运行）。
  - `publish_from_generated.py` + `x_publisher.py`：发布链路（本轮不运行）。
  - `enrichment/`：source_pack / fact_pack / 自动检索增强（含可能触发付费模型/联网检索的脚本，本轮不运行）。
- `configs/`
  - `integration_sources.json`：Integration API 数据源配置（base_url/paths/limit/enabled）。
  - `source_registry.json` / `source_pack_schema.json`：来源分层与 source_pack 结构约束。
  - `autopublish_rules.json`：发布硬门禁规则（本轮不运行）。
- `prompts/` + `skills/`：生成提示词与技能输入/输出 schema（X 内容结构约束）。
- `docs/`：运行手册、source research、visual pipeline 等文档。

## Q1. 当前热点源在哪里接入？

- Integration API（当前主接入）：
  - 入口：`scripts/run_hot_engine_once.py` 调用 `adapters.import_integration_api.fetch_pool()` 拉取 ready/published 池，再 `normalize_to_hot_input()` 归一化为内部 hot_input。
  - 关键代码：[run_hot_engine_once.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/run_hot_engine_once.py#L289-L336)、[import_integration_api.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/adapters/import_integration_api.py#L82-L128)
  - 配置：`configs/integration_sources.json`（本次审计不展开打印 base_url）。
- 外部信号源（Traffic Signal）：
  - 配置样例：`configs/hot_sources/trump_chinese_macro_sources.json`，但当前 Hot Engine 主入口明确“未接入 external_signal_source 到主输入”。
  - 证据：[run_hot_engine_once.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/run_hot_engine_once.py#L283-L286)

## Q2. 当前 candidate/input schema 是什么？

当前 pipeline 有两类“输入 schema”：

1) Hot Engine 的 `hot_input`（热点素材条目）：
- 来自 Integration API item，经 `normalize_to_hot_input()` 归一化得到，核心字段：
  - `input_id/source_platform/source_name/source_type/content_type`
  - `title/short_title/raw_text/source_url`
  - `received_at/published_at/event_fingerprint/pipeline_stage/category`
- 位置：[import_integration_api.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/adapters/import_integration_api.py#L53-L79)

2) LLM Skill 的输入契约（给生成器的结构化输入）：
- `skills/coinmeta_hot_post/input_schema.json`：以 `event_cluster_id/cluster_title/cluster_queue` 为中心，并允许携带 `best_source_url/source_urls/missing_facts/raw_summary/fact_pack` 等。
- `skills/coinmeta_whale_digest/input_schema.json`：whale digest 栏目型输入（actors/time_window 等）。

## Q3. 当前 normalize 在哪里？

- Integration API → hot_input：`normalize_to_hot_input()`。
  - 位置：[import_integration_api.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/adapters/import_integration_api.py#L53-L79)
- 聚类前文本归一：`rules/event_cluster.py` 的 `_norm_text()` 对标题/正文做 lower/空白压缩/标点替换等。
  - 位置：[event_cluster.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/rules/event_cluster.py#L35-L52)

## Q4. 当前 event cluster 在哪里？

- `rules/event_cluster.py:cluster_hot_inputs()`：6 小时窗口内聚类，优先 pattern_key，其次 event_fingerprint 相似度，其次关键词集合交集。
- 位置：[event_cluster.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/rules/event_cluster.py#L155-L247)

## Q5. 当前 queue split 在哪里？

- `rules/hot_engine_rulebook.py:evaluate_event()` 给每个 cluster 打分并决定 `cluster_queue`：
  - `queue_review / source_research / monitor / reject / whale_digest`
- 位置：[hot_engine_rulebook.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/rules/hot_engine_rulebook.py#L485-L772)

## Q6. 当前规则评分在哪里？

- 同样在 `rules/hot_engine_rulebook.py`：
  - `topic_priority()`：P0~P3
  - `audience_reach_score()`：受众面/用户连接点/传播钩子等
  - `select_best_source()` + `_best_source_rank()`：来源一手性分层
  - `total_score`：综合 `source_score/fact_score/heat_score/content_score/angle_score`
- 位置示例：[hot_engine_rulebook.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/rules/hot_engine_rulebook.py#L448-L517)

## Q7. 当前输出哪些队列？

Hot Engine（运行一次）会落盘以下队列文件（MD + events.jsonl）：

- `out/hot_engine_queues/queue_review.md`
- `out/hot_engine_queues/source_research.md`
- `out/hot_engine_queues/monitor.md`
- `out/hot_engine_queues/reject.md`
- `out/hot_engine_queues/whale_digest.md`
- 以及 `out/hot_engine_queues/rule_audit.md`、`out/hot_engine_queues/events.jsonl`

代码位置：[run_hot_engine_once.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/run_hot_engine_once.py#L351-L362)

## Q8. 当前 OpenRouter / Claude 调用入口在哪里？

- 统一入口：`scripts/llm_client.py`
  - runtime 开关：`MODEL_RUNTIME=mock|openrouter`（默认 mock，不走网络）。
  - OpenRouter HTTP 入口常量：`OPENROUTER_BASE_URL="https://openrouter.ai/api/v1/chat/completions"`
  - 位置：[llm_client.py](file:///c:/Users/zhuo7/Desktop/X自动化/x_automation/scripts/llm_client.py#L15-L43)
- 实际生成调用方：`scripts/generate_from_queue.py`（本轮不运行）。

## Q9. 当前 X 内容输出结构是什么？

以 skill 输出 JSON 为主（之后可被发布脚本消费）：

- `skills/coinmeta_hot_post/output_schema.json`（核心字段）：
  - `main_post`（主帖）
  - `first_comment`（首评/跟帖）
  - `visual_prompt`（配图提示）
  - `editor_risk_note/need_fact_check/weak_points`（审核/风控辅助）
- `skills/coinmeta_whale_digest/output_schema.json`：同字段，但语义面向栏目汇总。

发布脚本消费结构：
- `publish_from_generated.py` 从生成 JSON 读取 `main_post/first_comment`，通过 guard 后交给 `x_publisher.py`（本轮不运行）。

## Q10. 当前哪些地方属于 X 专属输出，不应该放进共享层？

建议判定为 X 专属（X Adapter 层）：

- X 内容生成的 prompt / style / template：
  - `skills/`、`prompts/`、`style/`、`templates/`
- X 发布/发布前门禁：
  - `scripts/publish_from_generated.py`
  - `scripts/x_publisher.py`
  - `scripts/autopublish_guard.py` + `configs/autopublish_rules.json`
- 视觉路线（面向 X 多形态输出的结构与 prompt pipeline）：
  - `scripts/visual/*` + `configs/visual_*`

这些模块强绑定 X 的输出形态与平台策略，不应放到共享 Hotspot Core。

## Q11. 当前哪些地方会和文章自动化重复建设？

更像可抽到共享 Hotspot Core（或至少 schema 统一）的部分：

- 热点源接入与归一化（ingestion + normalize）：
  - `scripts/adapters/import_integration_api.py`
  - `configs/integration_sources.json`
- 聚类（event cluster）：
  - `scripts/rules/event_cluster.py`
- 规则层的“事件评估输出”（至少输出字段集可以对齐到统一 event_pack）：
  - `scripts/rules/hot_engine_rulebook.py:evaluate_event()`
- source_pack / fact_pack（事实锚点与一手来源补齐的结构与流程）：
  - `configs/source_pack_schema.json`
  - `scripts/enrichment/fact_pack_builder.py`、`scripts/enrichment/build_enriched_queue.py`

潜在重复建设点（需要后续 bridge plan 统一 schema，避免双份定义）：
- `fact_pack` 的字段语义与枚举（confirmed/uncertain/should_not_claim）
- `event_type` / `risk_flags` / `recommended_outputs` 的枚举与落盘位置

## 审计结论（本轮）

- 当前 X 项目已有可用的“热点→聚类→规则→队列落盘”主链路，且 Hot Engine 本身不依赖模型调用。
- 本轮共享层切分建议：
  - 共享 Hotspot Core：ingestion/normalize/cluster/evaluate_event 的统一中间输出（event_pack）。
  - X Adapter：X 风格化内容生成、visual 路线、AI Reviewer/Risk Auditor gate、发布与日志/表现回收。
