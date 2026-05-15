# coinmeta_hot_post

## 作用

用于 Hot Engine 的 `queue_review` 事件：把事件聚合包（event_pack）写成 CoinMeta 中文 X 官号草稿（主帖 + 首评 + 配图提示 + 编辑风控）。

## 调用链（概念流程）

Hot Engine  
↓  
queue_review events（事件级队列）  
↓  
event_pack_builder（把事件信息打包成 event_pack）  
↓  
coinmeta_hot_post Skill  
↓  
OpenRouter Claude  
↓  
输出主帖 / 首评 / 风险提示（供人工审核或后续 dry-run 发布）

## 边界

- 本 Skill 不做事实判断（事实由 rulebook + best_source + missing_facts 决定）
- 本 Skill 不做联网检索补来源
- 不暗示跟单、不做投资建议

