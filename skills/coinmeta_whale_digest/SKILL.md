---
name: "coinmeta_whale_digest"
description: "生成「今天巨鲸在干嘛」栏目稿。用于拿到 actor_daily_pack（巨鲸/聪明钱聚合包）时，输出主帖/首评/配图提示/风控提示；必须基于素材，不编造交易。"
---

# CoinMeta Whale Digest Skill

## 用途

把「whale_digest」队列里同一时间窗内的巨鲸/聪明钱/高关注交易员行为，整理成一条可发布前的栏目草稿（主帖+首评），而不是逐条交易流水账。

## 触发条件（何时用）

- 已经完成 Hot Engine 分流，拿到当日/当周的 `actor_daily_pack`
- 需要做栏目化汇总：「今天巨鲸在干嘛」
- 需要在不喊单、不做投资建议的前提下，给出人话总结 + 风险边界 + 可核验点

关键词触发（任一命中即可视为适用）：

- whale_digest
- 今天巨鲸在干嘛
- 链上大户日报
- 麻吉
- 巨鲸调仓
- 明星地址
- 高关注交易员
- 仓位变化
- 清算风险

不要用于：
- 单条快讯的官号主帖生成（那走现有 CoinMeta Generate Prompt）
- 需要联网检索补来源的场景（本 Skill 不做检索）

## 输入要求

- 输入必须是 `actor_daily_pack`（聚合包），不是单条交易
- 必须提供：时间窗、生成时间、actors 列表
- 每个 actor 必须包含：为什么入选、净方向/净额、关键动作、来源链接、置信度、不可主张点

详见 [input_schema.json](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/skills/coinmeta_whale_digest/input_schema.json)

## 输出要求

- 输出必须严格符合 [output_schema.json](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/skills/coinmeta_whale_digest/output_schema.json)
- 必须基于输入素材：不得编造交易、不得补地址、不得补截图、不得暗示“跟单”
- 必须避免流水账：不要逐条列 transaction；要总结「今天整体在干嘛」
- 风格：CoinMeta 中文 X（短句、直白、有判断但克制）

## 安全边界

- 不输出投资建议、不做收益承诺、不写价格预测
- 对低置信度信息必须提示 `need_fact_check=true` 并在 `weak_points` 中点出缺口
- `editor_risk_note` 用于编辑审阅边界（如：避免把“可能清算”写成“即将爆仓”）

## 文件清单

- prompt： [prompt.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/skills/coinmeta_whale_digest/prompt.md)
- 输入 schema： [input_schema.json](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/skills/coinmeta_whale_digest/input_schema.json)
- 输出 schema： [output_schema.json](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/skills/coinmeta_whale_digest/output_schema.json)
- 示例： [examples.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/skills/coinmeta_whale_digest/examples.md)
- 调用说明： [README.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/skills/coinmeta_whale_digest/README.md)
