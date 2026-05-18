# Hot Engine v0.1（Internal DB / Integration API）Runbook

v0.1 的主链路只跑内部数据源（internal_db / Integration API 内容），不接入外部 X 账号抓取。

相关背景文档：
- [data_source_priority_v0.1.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/docs/data_source_priority_v0.1.md)

## v0.1 目标

- 把内部数据库/Integration API 的内容聚类为“事件”
- 用规则把事件分流到不同队列（queue_review / source_research / monitor / reject / whale_digest）
- 输出可人工审核的队列文件与审计记录（rule_audit / events.jsonl）
- 目标是“可审核内容候选”，不是自动发布

## 数据源优先级

- internal_db / Integration API：优先、也是 v0.1 主链路唯一输入来源
- external_signal_source：暂缓（例如 `@trumpchinese1` 只作为未来 external_signal_db 的设计草稿，不进入 v0.1 主流程）

## v0.1 不做的事（明确边界）

- 不做泛化外部抓取（不把任意外部 X 账号纳入输入）
- 不把 external_signal_source 当成事实源（fact_source）
- 不自动发布（auto_publish）与不做 direct_newsflash

## 今日真实 run 暴露的问题

本次真实运行统计：
- fetched_inputs=50
- clusters=27
- queue_review=0
- source_research=12
- monitor=8
- reject=6
- whale_digest=1

判断：
- 系统主链路可跑（Integration API → 聚类 → 分流 → 输出队列与审计文件）
- 但 queue_review=0 说明当前规则可能过保守，导致“可转内容候选”全部被压到 source_research/monitor
- 明天测试必须关注 near_miss（差一点就该进 queue_review 的候选）
- 不能只看 queue_review 数量，还要看 monitor/source_research 里是否存在被低估的好内容（潜在可升级事件）

## 运行命令

从 Integration API 拉取并跑一次 Hot Engine：

```bash
python scripts/run_hot_engine_once.py --source integration_published --limit 50
```

常用参数（用于明天跑一天时做增量/筛选）：

```bash
python scripts/run_hot_engine_once.py --source integration_published --limit 50 --offset 0
python scripts/run_hot_engine_once.py --source integration_published --limit 50 --since "2026-05-18T00:00:00Z"
python scripts/run_hot_engine_once.py --source integration_published --limit 50 --q "关键词"
python scripts/run_hot_engine_once.py --source integration_published --limit 50 --source "CoinMeta"
python scripts/run_hot_engine_once.py --source integration_published --limit 50 --content_type "newsflash"
```

说明：
- 若出现 fetch_failed，请检查 `configs/integration_sources.json` 的 base_url 是否可访问（该 Integration API 属于内部数据源配置的一部分）。

## 输出目录说明

运行后输出到：
- `out/hot_engine_queues/`

文件清单：
- `queue_review.md`：待审核的“可转内容候选”事件
- `source_research.md`：题材可能值得做，但缺事实锚点/来源，需要补证据
- `monitor.md`：有一定意义但不适合立刻发，放监控池
- `reject.md`：低价值/低受众面/难转化/风险不合适，拒绝
- `whale_digest.md`：链上/巨鲸/仓位类事件更适合汇总栏目
- `rule_audit.md`：规则审计（每条事件的最终队列、分数、缺失事实提示等）
- `events.jsonl`：机器可读事件记录（便于回放/二次分析）

## 每个队列含义（与规则口径对齐）

### queue_review

- 典型条件：受众面达标 + P0/P1 题材 + 事实硬（source_score/fact_score 较高）+ 有最佳来源 + 可转化为中文 X 角度
- 人工目标：判断是否适合官号、是否需要补事实、是否适合视觉化，然后决定进入后续生成流程或降级

### source_research

- 典型条件：题材受众面够，但事实不够硬（例如最佳来源层级偏低/缺关键链接/缺链上锚点）
- 人工目标：补“可回溯的一手来源/权威报道/链上地址/看板链接”等，再评估是否能升级到 queue_review

### monitor

- 典型原因：行业可能有意义，但当前受众面/用户连接点/事实不足；或属于常规信息（例如普通 ETF 资金流无强钩子）
- 人工目标：记录为趋势信号，等待更强钩子/更多事实出现

### reject

- 典型原因：受众面过窄、普通公告/参数更新、圈内术语堆叠难转化、传播价值低等
- 人工目标：确认拒绝合理；若出现明显误杀，记录并提出规则修改建议

### whale_digest

- 定位：链上/巨鲸/仓位变化更适合做“每日汇总栏目”，不默认按单条硬推
- 人工目标：把“可讲的重点 + 风险边界 + 需要的锚点”记录下来，作为栏目素材

## 人工审核方式（建议顺序）

1) 先看 `queue_review.md`
- 逐条填单条事件记录模板（见测试日志模板文档）
- 标注：是否适合官号、是否需要事实增补、是否适合视觉化

2) 再看 `source_research.md`
- 按 `missing_facts` 提示补证据类型（链接/地址/看板/权威报道）
- 记录“补齐后能否升级”的判断标准

3) 最后扫 `monitor.md` 与 `reject.md`
- 抽样核查：是否存在明显误判（应进 queue_review 的被放进 monitor/reject；或反之）

4) 用 `rule_audit.md` 回查一致性
- 核对：selected_queue 与 rule_reason 是否能解释结果
- 抽样对照：同类事件在不同批次是否稳定落同一队列

## 明天如何跑一天（建议流程）

建议采用“多次小批量 + 严格记录”的方式跑一天，避免一次性大批量导致审核不可控。

### A. 固定批次节奏

- 每次运行使用固定 limit（例如 50）
- 每次运行后立刻：
  - 记录本次统计（输入数量/聚类数量/各队列数量）
  - 从每个队列挑 1–3 条做“典型好样本/典型误判”记录

### B. 输出留档方式

- 每次运行后，把 `out/hot_engine_queues/` 里的关键输出复制/重命名为带时间戳的归档（至少保留 queue_review.md 与 rule_audit.md）
- 同时在测试日志里记录本次归档名，保证可回放

### C. 每日复盘点

- 中午/傍晚各做一次复盘：
  - 汇总“最高频误判类型”
  - 汇总“最影响官号产能的缺失事实类型”
  - 形成“需要改规则”的清单（只记录建议，不在今天改主逻辑）

## 如何记录问题（Issue Logging）

统一使用测试日志模板：
- [hot_engine_real_test_log_template.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/docs/hot_engine_real_test_log_template.md)

记录原则：
- 可复现：写清本次运行的参数（source/limit/offset/since/q 等）与对应输出归档
- 可定位：在单条事件记录里写明 cluster_title、selected_queue、rule_reason（若有）
- 可行动：把问题落到“需要改规则”的一句话建议（例如阈值、关键词、来源权重、缺失事实提示等）

## source_research 自动补源 v0.1

定位：
- 当前只做 mock（不联网、不调用 Claude、不调用搜索 API）
- 只处理 `source_research` 队列
- 不处理全量内容（monitor/reject/queue_review 全量不进入该流程）

v0.1 输出：
- 输出 `source_pack`（结构化补源结果包），用于判断是否可回推 `queue_review`

边界：
- 不进入自动发布，不生成可直接发布内容
- Trae 不负责执行真实 Claude 调用，不负责设置或读取任何 API Key

后续 v0.2 规划：
- 可接入 `anthropic_web_search` / Tavily / SerpAPI 等真实搜索提供方
- 必须先落实预算控制（每条最多 3 次 search、每日上限、缓存与去重）

相关文档：
- [source_research_auto_search_v0.1.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/docs/source_research_auto_search_v0.1.md)
- [source_research_auto_search_cost_claude.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/docs/source_research_auto_search_cost_claude.md)
