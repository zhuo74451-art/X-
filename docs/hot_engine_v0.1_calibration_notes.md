# Hot Engine v0.1 Calibration Notes（Near Miss / 误判优先级）

## 为什么 queue_review=0 不是马上失败，但必须校准

- v0.1 的目标是把内部数据源稳定跑通：拉取 → 聚类 → 分流 → 输出可审核队列与审计记录
- queue_review=0 不代表系统不可用，可能代表“阈值/规则过保守”，把潜在好内容压到了 source_research/monitor
- 如果不做校准，系统会出现“主链路可跑但产能为 0”的状态：每天跑得动，但没有可转内容候选

## 为什么需要 Near Miss Candidates

Near Miss 的定义：按当前规则没有进入 queue_review，但从人工判断看“差一点就该进 queue_review”的事件候选。

Near Miss 的价值：
- 能快速定位“差的不是题材，而是阈值/缺失事实提示/用户连接点识别”等可调部分
- 能把校准从“拍脑袋改规则”变成“围绕可升级样本做定点修正”
- 能衡量优化效果：near_miss_count 是否下降、monitor_to_review_transition 是否上升

## 明天的记录节奏（每 2 小时一次）

- 明天从开始跑起，每 2 小时记录一次队列数量与 Near Miss 指标
- 记录表使用：
  - [hot_engine_real_test_log_template.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/docs/hot_engine_real_test_log_template.md)

## 明天人工抽查策略（固定配额）

- queue_review：全看
- source_research：抽 10 条
- monitor：抽 10 条
- reject：抽 10 条（重点找假阴性）

抽查目标：
- 从 source_research/monitor 里挑 Near Miss，记录 top_near_miss_title 与可升级原因
- 从 reject 里重点找“假阴性”（本应保留/可研究/甚至可审核的事件）

## 最危险的误判类型（按优先级）

1) reject false negative（最高危险）
- 含义：真正值得做的事件被直接丢进 reject，导致“丢题材/丢机会”，且后续很难被捞回
- 明天动作：reject 抽查优先、单条记录必须写清“为什么不该 reject”

2) whale false trigger 与 macro_plain false trigger（第二危险）
- whale false trigger：非链上/巨鲸类事件被错误分到 whale_digest，稀释栏目素材并误导分流
- macro_plain false trigger：本应有现实场景/用户连接点的宏观议题被当作宏观空话压到 monitor/reject
- 明天动作：分别统计 whale_false_trigger_count 与 macro_plain_false_trigger_count，并记录典型标题

## 明日测试重点：Near Miss 校准

1) 明天不要只看 queue_review
- queue_review 是“可转内容候选”的显性出口，但当规则过保守时，真正值得做的内容会被压到 source_research/monitor
- 因此明天的目标是：用 Near Miss 把“被低估的好内容”系统性地标出来

2) queue_review=0 不代表系统失败
- queue_review=0 的含义是：当前规则没有给出任何“直接进入审核候选”的事件
- 但系统仍可能在 source_research/monitor 里产生大量可升级候选，这正是校准的价值所在

3) 每 2 小时记录一次（固定字段）
- queue_review
- near_miss_count
- source_research
- monitor
- reject
- whale_digest

4) 每次重点人工看 Near Miss Top 10
- Top 10 的来源：优先从 source_research 与 monitor 中挑“差一点”的事件
- Top 10 的目标：让人工把注意力集中在“最可能升级、最可能代表当天重要事件”的候选上

5) 标记每条 Near Miss（四选一）
- should_review
- needs_source_research
- should_monitor
- should_reject

6) 明天最重要指标（校准是否有效）
- Near Miss Top 10 是否覆盖当天真正重要事件
- source_research 里有多少能被补源后转入 review
- reject 是否有假阴性
- whale false trigger 是否消失
- macro_plain false trigger 是否消失
