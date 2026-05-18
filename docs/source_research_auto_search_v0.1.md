# source_research_auto_search v0.1（使用说明）

v0.1 默认只跑 mock：不联网、不调用 Claude、不调用任何搜索 API，用于打通“补源结构与审计输出”的最小闭环。

## 目标

把 Hot Engine 的 `source_research` 队列变成“可回放的补源结果包（source_pack）”，用于决定某个事件是否有资格被推回 `queue_review` 进入人工审核与后续生成流程。

## 输入

- 输入范围：仅 `source_research` 队列事件
- 输入载体（推荐）：`out/hot_engine_queues/` 的运行产物（例如 source_research.md / events.jsonl / rule_audit.md）
- 输入字段核心依赖（概念）：cluster_id、cluster_title、missing_facts、best_source_url/source_urls、source_names 等

说明：v0.1 不处理全量事件（monitor/reject/queue_review 全量），只做 source_research 的“补源与升级判断”。

## 输出

输出为 `source_pack`（逐事件产出一份），建议结构包含：

- run_id / generated_at：便于回放
- event_cluster_id / cluster_title：定位事件
- search_queries：本次使用的 query 列表（用于缓存与去重）
- candidate_sources：候选来源列表（标题、域名、URL、时间、匹配理由）
- verification_status：`verified` / `partial` / `not_found` / `conflict`
- can_promote_to_queue_review：bool
- promote_reason / block_reason：升级或阻止升级的原因
- notes：人工补充（可选）

## source_pack 字段说明

- verification_status
  - verified：找到可回溯且一致的关键来源，能满足 missing_facts 的主要缺口
  - partial：找到部分来源或只能补一部分事实锚点，暂不足以升级到 queue_review
  - not_found：未找到与事件强相关且可回溯的来源
  - conflict：搜索结果之间存在关键冲突（时间线/主体/数字/结论冲突），必须人工复核，默认不允许升级

- can_promote_to_queue_review
  - true：允许把该事件标记为“可回到 queue_review”
  - false：保持在 source_research/monitor，或直接判定不应升级

## mock 模式用法（v0.1 默认）

默认配置：
- `SEARCH_PROVIDER=mock`
- `MODEL_RUNTIME=mock`

mock 模式下的行为：
- 不进行真实搜索
- 不调用 Claude
- 仍会生成 source_pack 的结构化骨架（例如：search_queries 占位、candidate_sources 为空、verification_status 为 not_found/partial 的占位输出）
- 目的是让输出格式、审计字段、缓存键、promote 规则可以先被验证与讨论

## 真实搜索模式未来规划（v0.2）

当 v0.1 的结构与审计输出稳定后，v0.2 才考虑接入真实搜索与模型运行时，例如：
- `anthropic_web_search`
- Tavily
- SerpAPI

注意：接入真实搜索意味着成本与风险上升，因此必须先落地预算控制与缓存策略。

## v0.2-light：真实搜索 provider 开关版

v0.2-light 的定位是“真实搜索 provider 开关版”，只补齐真实搜索的开关与候选来源输出，不引入模型判断与自动 promote。

- 默认仍是 mock：不联网、不调用任何搜索 API
- 用户显式设置 provider 后才会真实搜索（没有显式设置就不会发生任何联网行为）

当前 v0.2-light 约束：
- 当前只支持：tavily / brave / serpapi
- anthropic_web_search 暂不实现
- Claude 判断暂不实现（不做模型对搜索结果的可靠性判定）

关于结果含义：
- 真实搜索结果只生成 candidate_sources（候选来源列表），不等于 verified
- 需要人工复核或后续引入 Claude 判断后，才能 promote（推回 queue_review）

## 不能直接自动发布

- source_research_auto_search 的产物只用于“补源与升级判断”
- 即使 can_promote_to_queue_review=true，也只是“回到 queue_review 进入人工审核”
- 不允许直接进入 auto_publish，不允许 direct_newsflash，不允许把二手来源当作直接引用对象

## can_promote_to_queue_review 的条件（v0.1 口径）

满足以下约束才允许 promote（默认策略，后续以规则层实现为准）：

- 只处理 source_research 队列事件（非该队列不处理）
- 每条最多 3 次 search（v0.2 引入真实搜索时强制）
- 没有 P0/P1 来源，不允许 promote_to_queue_review
- 搜索结果冲突（conflict），不允许 promote
- 只有中文搬运号/二手聚合号，不允许 promote
- 缺失事实无法补齐或只能 partial，不允许 promote

关联成本与预算控制详见：
- [source_research_auto_search_cost_claude.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/docs/source_research_auto_search_cost_claude.md)

## 用户如何手动开启真实模式（仅文档说明）

默认不启用真实调用。未来若要启用，由用户在 PowerShell 当前窗口手动设置环境变量：

```powershell
$env:ANTHROPIC_API_KEY="你的 key"
$env:SEARCH_PROVIDER="anthropic_web_search"
$env:MODEL_RUNTIME="claude"
```

并执行（若脚本存在）：

```bash
python scripts/enrichment/source_research_auto_search.py --run-dir out/hot_engine/<run_id>
```

说明：
- Trae 不负责执行真实 Claude 调用，不负责设置或读取 API Key。
- 文档只描述流程与预算规则，不包含任何 Key 或外部调用示例输出。
