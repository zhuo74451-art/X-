# source_research_auto_search v0.1：Claude 成本与预算控制

## 1. 当前定位

`source_research_auto_search v0.1` 只处理 Hot Engine 输出的 `source_research` 队列，不处理全量内容。

目标不是自动写稿，而是形成“可回放的补源证据包”：

source_research  
→ 生成搜索 query  
→ 搜索候选源  
→ 生成 source_pack  
→ 判断是否可以推回 queue_review  

## 2. 为什么不能只靠 Prompt

- 模型不能凭空检索最新来源。
- 只有接入真实 web_search tool / 搜索 API / function calling，模型才有搜索能力。
- 如果没有搜索工具，只在 prompt 里写“请检索最新来源”，容易出现：
  - 伪造来源（fabricated citations）
  - 旧闻新发（把历史新闻当作最新）
  - 错配相似事件（把相近标题/相近人物的新闻当成同一事件）

因此 v0.1 默认 mock 的意义是：先把流程与审计结构跑通，再在 v0.2 引入真实搜索。

## 3. Claude 成本假设

Claude Haiku：
- input $0.80 / 1M tokens
- output $4 / 1M tokens

Claude Sonnet：
- input $3 / 1M tokens
- output $15 / 1M tokens

Claude Opus：
- 不用于常规流水线，只用于人工指定的重要复核

Anthropic web search：
- 约 $10 / 1000 searches
- 约 $0.01 / search

说明：具体价格以后以 Anthropic 官方 pricing 为准，本文档仅用于当前预算估算与上限控制。

## 4. 单篇成本估算

不联网，只写稿：
- Haiku：约 $0.01–0.02 / 篇
- Sonnet：约 $0.04–0.06 / 篇

联网补源 + 写稿，假设 3 次搜索：
- Haiku：约 $0.05 / 篇
- Sonnet：约 $0.10–0.12 / 篇

## 5. 月度成本估算

按照 source_research 数量估算（假设“联网补源 + 写稿”）：

20 条/天：
- Haiku 补源：约 $30–40/月
- Sonnet 补源：约 $60–80/月

50 条/天：
- Haiku 补源：约 $75–100/月
- Sonnet 补源：约 $150–180/月

100 条/天：
- Haiku 补源：约 $150–200/月
- Sonnet 补源：约 $300–360/月

强调：最大成本风险不是写稿，而是全量搜索。任何“对全量事件做搜索”的策略都会迅速放大成本与不确定性。

## 6. 推荐模型分工

Haiku：
- search query 生成
- source_research 初筛
- 搜索结果粗判

Sonnet：
- 最终 source_pack 判断
- 正式稿生成
- 高价值事件复核

Opus：
- 不进常规流水线
- 只用于特别重要内容人工指定复核

## 7. 预算控制规则

- 每条 source_research 最多 3 次 search
- 每批最多处理 20 条 source_research
- 每日最多 100 次 search
- 同一 cluster_id 24 小时内只搜索一次
- 同一 search_query 24 小时缓存
- 没有 P0/P1 来源，不允许 promote_to_queue_review
- 搜索结果冲突，不允许 promote
- 只有中文搬运号，不允许 promote

## 7.1 Gemini 顾问建议（成本与策略）

- 这是低成本、高价值的精锐部队策略：只把“最可能被救回 queue_review 的事件”拿去做补源
- 不要全量搜索：全量搜索是最大成本风险与噪声来源
- 只搜索 source_research：把预算集中在“差一点就能升级”的队列
- 推荐 2+1 搜索策略：
  - 2 次主流/权威搜索（找 Reuters/Bloomberg/官方文件/监管网站等）
  - +1 次补充搜索（针对关键实体/数字/时间线做交叉确认）
- 单条成本约 $0.05 左右（含约 3 次 search 的量级）
- 每天 20 条约 $30/月
- 每天 50 条约 $75–100/月
- 每天 100 条约 $150–200/月
- 对我们每天只发几条的场景，成本可控，关键是“不要把搜索扩展到全量事件”

## 7.2 预算 Hard Cap（上限控制）

- 每条最多 3 次 search
- 每批最多 20 条
- 每日最多 100 次 search
- 单小时超过 $10 自动停止（后续实现 kill switch）
- cluster_id / query 24h 缓存（避免重复搜索）

## 8. 用户如何手动开启

默认：
- `SEARCH_PROVIDER=mock`
- `MODEL_RUNTIME=mock`

未来真实开启 Claude 时，由用户自己在 PowerShell 当前窗口设置：

```powershell
$env:ANTHROPIC_API_KEY="你的 key"
$env:SEARCH_PROVIDER="anthropic_web_search"
$env:MODEL_RUNTIME="claude"
```

然后运行（若该脚本已在项目中提供）：

```bash
python scripts/enrichment/source_research_auto_search.py --run-dir out/hot_engine/<run_id>
```

注意：
- Trae 不负责执行真实 Claude 调用，不负责设置或读取 `ANTHROPIC_API_KEY`。
- 本项目文档不保存任何 API Key；不要把 Key 写进仓库文件、日志、截图或样本数据。
