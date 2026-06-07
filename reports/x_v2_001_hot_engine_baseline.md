# X v2-001 Hot Engine Baseline（一次运行记录）

目标：跑一次现有 Hot Engine 基线；不调用付费模型；不真实发布 X。

## 运行尝试 1（按 README：integration_published）

命令：

```powershell
$env:MODEL_RUNTIME="mock"
python scripts/run_hot_engine_once.py --source integration_published --limit 50
```

结果：失败（blocked）

- blocked_reason: `fetch_failed http error: 502`
- 失败点：Integration API 拉取阶段（`adapters/import_integration_api.py:_http_get_json` → HTTPError）
- 影响：未生成 `out/hot_engine_queues/*`，也未生成 `out/hot_engine/<run_id>/...`

## 运行尝试 2（只读离线基线：offline fallback，用于验证队列结构）

说明：
- 该 fallback 不替代 integration_published 的真实基线，只用于在数据源不可用时验证“聚类→规则→队列落盘”流程可跑通与输出结构。
- 输入来自仓库内样例：`data/sample_hot_inputs.json`

命令：

```powershell
python scripts/run_hot_engine_offline_once.py --input-file data/sample_hot_inputs.json
```

运行输出（stdout 摘要）：
- inputs: 21
- clusters: 21
- queue_review: 0
- source_research: 8
- whale_digest: 0
- monitor: 8
- reject: 5

落盘目录：
- `out/hot_engine_queues_offline/20260607T114605Z/`

目录内产物：
- `queue_review.md`
- `source_research.md`
- `monitor.md`
- `reject.md`
- `whale_digest.md`
- `rule_audit.md`
- `events.jsonl`
- `operator_summary.md`

## 关键结构记录（来自 events.jsonl）

Hot Engine 的事件级输出（每行一个 event）核心字段（节选）：
- `event_cluster_id/cluster_title/cluster_queue`
- `topic_priority/audience_reach_score/total_score`
- `best_source_item_id/best_source_rank/best_source_url/source_urls`
- `missing_facts/rule_reason/risk_level`
- whale digest 相关字段：`actor_label/asset/action/amount_usd/...`

## top_candidates（offline fallback Top 10）

按 `total_score` 降序（只列 title/queue/score）：

1) (76) source_research — Lookonchain：某巨鲸地址在过去 12 小时内将一批 资产分批转入交易所，并在链上出现多次小额测试转账。
2) (76) source_research — 数据：BTC 长期持有者供应占比上升，短期持有者活跃下降，交易所余额继续走低。
3) (68) source_research — 数据：某交易对资金费率持续为正但未创新高，清算量集中在短时间窗口。
4) (66) source_research — 【快讯】某头部交易所宣布下调现货手续费并上线「一键批量撤单」功能，称将改善高频交易体验。
5) (66) source_research — 某交易所出现「暂停提币」传闻，截图来源不明，评论区开始扩散恐慌。
6) (62) source_research — 【快讯】某钱包应用上线「地址风险提示」与「授权一键清理」入口。
7) (62) source_research — IEA 月报称，受伊朗战争影响，2026 年全球石油供 应预计减少约 390 万桶/日，全球石油库存正以创纪录速度下降。另
8) (58) monitor — Whale Alert：一笔大额稳定币跨链转移完成，目标链上的 DeFi 头部池子出现流动性变化。
9) (58) monitor — 一段短视频在社区传播：把「链上授权」拍成一键开门的钥匙，最后钥匙丢了导致家门大开，评论区大量讨论授权风险与钓鱼。
10) (58) monitor — 空投来啦！私信我进群，保证稳赚不赔，最后一班车，冲 1000x！

## 本轮结论

- integration_published 数据源当前不可用（HTTP 502），基线运行被阻塞；未对配置/代码做任何修复。
- 离线 fallback 验证了队列分桶与落盘结构满足“queue_review/source_research/monitor/reject/whale_digest + events.jsonl + operator_summary”的基线要求。
