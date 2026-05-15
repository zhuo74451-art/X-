---
name: "coinmeta_hot_post"
description: "生成 CoinMeta 官号热点主帖/首评草稿。用于 queue_review 的 event_pack（事件聚合包）生成可审核内容；必须基于输入，不编造事实。"
---

# CoinMeta Hot Post Skill

## 用途

用于 Hot Engine 的 `queue_review` 事件：把 event_cluster 聚合后的 `event_pack` 写成 CoinMeta 中文 X 官号草稿（主帖 + 首评 + 配图提示 + 编辑风控）。

## 触发条件

- 事件已进入 `queue_review`
- 已有 best_source / source_urls / missing_facts / rule_reason 等信息
- 需要可审核内容草稿，不自动发布

不要用于：
- whale_digest（巨鲸日报走 coinmeta_whale_digest）
- source_research（先补事实再说）

## 输入要求

输入必须是 `event_pack`（事件级聚合包），不是单条快讯。

详见 input_schema.json。

## 输出要求

输出必须是 JSON，符合 output_schema.json。

安全边界：
- 不做投资建议，不暗示跟单
- 不把二手信息写成确定事实
- 若缺事实锚点，必须在 editor_risk_note / need_fact_check / weak_points 中点明

