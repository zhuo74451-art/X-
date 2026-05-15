# coinmeta_whale_digest

## 作用

「今天巨鲸在干嘛」是一个独立栏目 Skill：输入是 `actor_daily_pack`（按 actor 聚合后的当日行为包），输出是一条 CoinMeta 中文 X 栏目草稿（主帖+首评+配图建议+编辑风控）。

它不替代现有官号 Generate Prompt，也不应被塞进整体官号 Prompt。

## 不做的事（边界）

- 不调用 Claude（本仓库目前只提供 Skill 文件与示例）
- 不联网检索补来源
- 不生成交易流水账
- 不暗示跟单、不做投资建议

## 调用链（概念流程）

hot_engine  
↓  
whale_digest events（事件级队列）  
↓  
actor_daily_pack_builder（把事件聚合成「按 actor」的日包：净方向/净额/风险变化/关键动作/来源链接）  
↓  
coinmeta_whale_digest_skill（本 Skill）  
↓  
OpenRouter Claude 输出（严格 JSON）  

## 文件

- prompt：prompt.md
- schema：input_schema.json / output_schema.json
- examples：examples.md
