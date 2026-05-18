# Hot Source：@trumpchinese1（特朗普中文推特）

结论：`@trumpchinese1` 只能作为 traffic_signal（流量信号源），不是 fact_source（事实源）。

## 账号定位

- 类型：X 平台中文转述/搬运/摘要账号
- 内容特征：以中文转述特朗普相关发言、采访片段、评论为主，可能包含二手转译与语境裁剪
- 风险：转述不等于原话；断章取义/错译/拼接的概率高于一手来源与权威媒体

## 为什么加入

- 目标用途：作为“热度与传播”线索，帮助发现可能需要跟进核查的议题
- 适用场景：当中文社区已开始传播某段话/某个争议点时，用它捕捉讨论正在升温的主题

## 允许用途（Allowed）

- 仅用于：发现候选话题、提取关键词、生成待核查的 research/monitor 任务
- 允许进入的队列/阶段：`traffic_signal` 或 `queued_verification`
- 允许输出的内容形态：内部审核材料、核查清单、需要补证据的要点列表

## 禁止用途（Forbidden）

- 禁止作为事实依据：不得把其中文转述当成“已确认事实”
- 禁止直接引用：不得在最终内容中以“引用该账号说法/截图/转述”为直接依据（no direct citation）
- 禁止自动发布：任何命中该源的内容不进入 `auto_publish`
- 禁止直出快讯：不进入 `direct_newsflash`

## Source-level Filter 规则（面向该账号的额外约束）

该账号默认应继承全局内容安全与垃圾过滤；同时增加以下 source-level 规则以降低误用风险：

- 允许但必须复核：涉及政策/监管/AI 护栏等“可讨论但需核查出处”的内容
  - 标记：`needs_verification = true`
  - 输出：只生成“核查提示/检索关键词/原文线索”，不生成可直接发布的事实陈述
- 中国国内敏感政治：一律拦截
  - block_reason：包含 `cn_sensitive_politics`
- 毒品相关：一律拦截
  - block_reason：包含 `drugs`
- 博彩/赌博相关：一律拦截
  - block_reason：包含 `gambling`

## 处理逻辑（Pipeline）

- 输入命中 `@trumpchinese1` →
- 运行 source-level filter →
  - allowed：进入 `traffic_signal` / `queued_verification`，并强制 `needs_verification=true`、`publish_as_source=false`
  - blocked：直接拒绝，不进入 Hot Engine，不触发内容生成/视觉生成
- 人工二次核查（必须）：
  - 优先核查英文一手来源：原始演讲/采访视频/白宫或竞选团队发布、权威媒体原文
  - 无法核查时：只允许保留为 monitor/research，不得升级为可发布内容

## 样本与预期

### 1) AI/政策（allowed，但 needs_verification）

- 文件：[source_filter_trumpchinese1_ai_policy_allowed.txt](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/data/samples/source_filter_trumpchinese1_ai_policy_allowed.txt)
- 预期：
  - source_filter_status = allowed
  - source_role = traffic_signal
  - needs_verification = true
  - publish_as_source = false
  - pipeline_stage = traffic_signal 或 queued_verification
  - 不进入 auto_publish / direct_newsflash

### 2) 中国国内敏感政治（blocked）

- 文件：[source_filter_trumpchinese1_cn_sensitive_blocked.txt](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/data/samples/source_filter_trumpchinese1_cn_sensitive_blocked.txt)
- 预期：
  - source_filter_status = blocked
  - block_reason 包含 cn_sensitive_politics
  - 不进入 Hot Engine / 内容生成 / 视觉生成

### 3) 毒品（blocked）

- 文件：[source_filter_trumpchinese1_drugs_blocked.txt](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/data/samples/source_filter_trumpchinese1_drugs_blocked.txt)
- 预期：
  - source_filter_status = blocked
  - block_reason 包含 drugs

### 4) 博彩（blocked）

- 文件：[source_filter_trumpchinese1_gambling_blocked.txt](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/data/samples/source_filter_trumpchinese1_gambling_blocked.txt)
- 预期：
  - source_filter_status = blocked
  - block_reason 包含 gambling

## 核查要求（强制）

- 不作为事实源：`@trumpchinese1` 只能作为 traffic_signal，不是 fact_source
- 命中后必须二次核查：至少核查英文一手来源或可靠媒体原文
- 不进入 auto_publish：任何由该源触发的条目必须走人工审核
- 不进入 direct citation：最终内容不得把该源当作“引用对象/证据来源”
