# source_research_auto_search：真实搜索使用说明（v0.2-light）

本说明只覆盖“真实搜索 provider 开关版”的使用方式与注意事项；不包含任何 API Key，也不在 Trae 内执行真实搜索。

## 1) 默认 mock 命令

mock（不联网）：

```bash
python scripts/enrichment/source_research_auto_search.py --run-dir out/hot_engine/<run_id> --provider mock
```

## 2) Tavily 手动开启方式

由用户在自己的 PowerShell 当前窗口设置 Key（不要写进仓库文件）：

```powershell
$env:TAVILY_API_KEY="你的 key"
python scripts/enrichment/source_research_auto_search.py --run-dir out/hot_engine/<run_id> --provider tavily --max-items 5
```

## 3) Brave 手动开启方式

```powershell
$env:BRAVE_SEARCH_API_KEY="你的 key"
python scripts/enrichment/source_research_auto_search.py --run-dir out/hot_engine/<run_id> --provider brave --max-items 5
```

## 4) SerpAPI 手动开启方式

```powershell
$env:SERPAPI_API_KEY="你的 key"
python scripts/enrichment/source_research_auto_search.py --run-dir out/hot_engine/<run_id> --provider serpapi --max-items 5
```

## 5) 缺 key 会报错

- 若 provider 选择 tavily/brave/serpapi 但未设置对应环境变量，脚本应报错或返回空结果（具体以脚本实现为准）。
- 处理方式：只在当前 PowerShell 会话临时设置 Key，然后重跑同一批次。

## 6) 不要在 Trae 中执行真实搜索

- Trae 不负责执行真实搜索、不负责执行真实 Claude 调用
- Trae 不负责设置、读取或保存任何 API Key
- 在 Trae 内执行真实搜索会带来不可控的成本与环境泄露风险

## 7) 用户在自己的 PowerShell 当前窗口设置 API Key

- 只在当前会话设置，不要写入代码/文档/样本/日志
- 不要把 Key 复制进任何仓库文件

## 8) 实测后看哪些文件

建议先看运行目录对应的输出（不同实现可能略有差异，以下为推荐口径）：
- 本次 run 的 source_pack 输出（逐事件的 candidate_sources、search_queries、状态字段）
- 运行日志中每条事件的 search 次数统计（用于预算核对）
- 若有：缓存命中信息（query/cluster_id 24h 去重）

也可回看 Hot Engine 原始队列文件用于对照：
- `out/hot_engine_queues/source_research.md`
- `out/hot_engine_queues/rule_audit.md`

## 9) 如何判断 source_pack 是否值得人工复核

优先人工复核的信号：
- candidate_sources 中出现 P0/P1 级别来源（官方公告/监管机构/权威媒体原文等）
- 多个候选来源在关键点一致（主体/时间/数字/动作一致）
- 明确补齐了 missing_facts 指向的“事实锚点”（原文链接/公告页/法院文件/链上地址/看板链接）

应谨慎或暂不复核的信号：
- candidate_sources 全是二手聚合/中文搬运号
- 候选来源之间出现关键冲突（时间线/主体/数字冲突）
- 搜索结果明显“相似事件错配”（同名人物/同类标题但不是同一事件）
