# Data Source Priority v0.1

第一版 Hot Engine 的主数据源是内部数据库（internal_db），不是外部 X 账号抓取。

结论：
- internal_db 优先，作为第一版的唯一“可运行主链路数据源”
- external_signal_source 只能作为 traffic_signal（流量信号），不作为 fact_source（事实源）
- 第一版不做泛化外部抓取；外部账号只保留为“监控源卡片 + 过滤规则草稿”

## 数据源优先级（Priority Order）

1) internal_db（P0）
- 定义：项目内部的结构化数据（本地 SQLite/JSON 导入后的结构化队列等），可追溯、可复跑、可审计
- 用途：Hot Engine 主流程的输入来源；生成 review/monitor/reject 等队列
- 要求：每条输入必须能在本地复现（同一条 raw_text、同一套规则、同一输出）

2) external_signal_source（P2）
- 定义：外部平台上的二手信号源（例如 X 的搬运/转述账号、频道、截图转述等）
- 用途：只用于“发现话题/热度”与“触发核查任务”
- 限制：不进入自动发布链路；不允许作为事实断言的依据

示例：
- `@trumpchinese1`：未来归入 `external_signal_db`（或更细分的 `trump_chinese_macro_signal_db`）；当前只作为监控源卡片与过滤规则草稿存在。

## external_signal_source 不作为事实源（Non-Fact Source）

external_signal_source 的定位是“线索”，不是“证据”：
- 只能触发：关键词提取、核查清单、需要回溯的一手来源提示
- 不能触发：直接快讯式发布、直接引用式发布、自动发布
- 命中后必须二次核查：优先英文一手来源或可靠媒体原文；无法核查则降级为 monitor/research

## traffic_signal 与 fact_source 的区别

### traffic_signal（流量信号）

- 目的：回答“大家在传什么/热度在哪”
- 输入来源：二手传播/转述/截图/搬运账号等
- 输出形态：待核查线索、监控卡片、核查 checklist
- 强制属性：`needs_verification = true`（或等效机制）
- 禁止：作为事实依据、直接引用、进入 auto_publish / direct_newsflash

### fact_source（事实源）

- 目的：回答“这件事是否发生/具体细节是什么”
- 输入来源：官方公告、原始文件、权威媒体原文、可追溯的一手材料
- 输出形态：可在审核后用于内容陈述与引用的证据链
- 要求：可回溯到原文链接或原始材料；可交叉印证；可被复核

## v0.1 不做的事（Non-Goals）

- 不做泛化外部抓取：不做“把任意 X 账号都拉进来”或“自动扩展抓取名单”
- 不做外部信号入库自动化：不建立 external_signal_db 的采集/同步/去重/归档全链路
- 不把 external_signal_source 当事实源：不把二手转述当作可发布的事实陈述

## 后续数据层规划（Future）

当 v0.1 的 internal_db 主链路稳定后，再逐步建设：

- `external_signal_db`
  - 目标：把外部信号源结构化入库（带 source_profile、风险标签、命中规则、可追溯记录）
  - 结果：外部信号可以被统一管理与回放，但仍默认不是 fact_source

- `trump_chinese_macro_signal_db`
  - 目标：为特朗普中文相关宏观议题建立更细分的信号库（账号、关键词、议题标签、典型误用风险）
  - 结果：更精确的“话题雷达”，更严格的“必须回溯英文一手来源”约束
