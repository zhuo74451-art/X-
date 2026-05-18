# Hot Engine Real Test Log Template

用于记录“跑一天”的批次统计与典型样本，目标是让问题可回放、可复现、可落到规则改动建议。

## 批次统计表（每次运行填一行）

| 时间 | 输入数量 | 聚类数量 | queue_review | monitor | reject | source_research | near_miss_count | top_near_miss_title | queue_review_false_positive | reject_false_negative | monitor_to_review_transition | source_research_success_rate | whale_false_trigger_count | macro_plain_false_trigger_count | 典型好样本 | 典型误判 | 需要改规则 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

建议填写口径：
- 输入数量：本次 fetch 到的 raw_items 条数
- 聚类数量：events 数量（可从 out/hot_engine_queues/rule_audit.md 的 Events 或终端输出统计取值）
- 典型好样本/典型误判：写 event_cluster_id 或 cluster_title（短句）+ 为什么
- 需要改规则：一句话落点（阈值/关键词/来源权重/缺失事实提示/队列分流等）

新增字段口径（建议）：
- near_miss_count：你认为“差一点就该进 queue_review”的事件数量（通常来自 monitor/source_research）
- top_near_miss_title：最典型 near_miss 的 cluster_title
- queue_review_false_positive：queue_review 中被你判定“不该进 queue_review”的数量
- reject_false_negative：reject 中被你判定“本应进入 monitor/source_research/甚至 queue_review”的数量（最高优先级关注）
- monitor_to_review_transition：从 monitor 人工判断可升级到 queue_review 的数量
- source_research_success_rate：source_research 抽查中，补齐事实后可升级的比例（例如 3/10）
- whale_false_trigger_count：误触发 whale_digest 的数量
- macro_plain_false_trigger_count：macro_plain 误触发导致被压到 monitor/reject 的数量

## 单条事件记录模板（对典型样本/误判必填）

```text
事件标题：
来源：
selected_queue：
hot_score：
source_score：
fact_score：
入队原因：
是否适合官号：
是否需要事实增补：
是否适合视觉化：
人工判断：
问题：
后续规则建议：
```
