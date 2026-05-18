# CoinMeta Hot Engine（本地闭环）

定位：中文 Web3 热点型准 KOL 官号系统（不是传统新闻自动化）。核心目标是把素材变成“可审核的内容候选”，而不是自动发布。

限制（不做）：
- 不接真实 X
- 不自动发布
- 不做浏览器自动化
- 不接 Telegram / 飞书
- 不做图片生成（只输出配图提示）
- 不做联网检索增强（除非进入后续阶段明确要求）
- 不把任何 API Key 写入代码/文档/日志

## 流量信号源（Traffic Signal）

- `@trumpchinese1`：仅作为 traffic_signal（不是 fact_source），命中后必须二次核查英文一手来源或可靠媒体；不进入 auto_publish / direct citation。详见 [hot_source_trumpchinese1.md](file:///c:/Users/PC/Desktop/x半自动运营/官号自动运营/coinmeta_x_hot_follow_engine/docs/hot_source_trumpchinese1.md)

## 当前架构（统一路线）

Hot Engine（规则层）  
↓  
Rulebook / Event Cluster / Queue Split  
↓  
Skill Prompt  
↓  
OpenRouter  
↓  
Claude  
↓  
官号 X 输出（主帖/首评/风控/配图提示）

说明：
- Hot Engine 当前以程序规则为主（Rulebook），不让 Claude 做前置规则判断
- 项目只支持 `MODEL_RUNTIME=mock` / `MODEL_RUNTIME=openrouter`

## 环境

- Python 3.x
- 依赖：仅标准库（sqlite3 / json / urllib 等）

## Hot Engine 运行（Integration API → 事件级队列）

```bash
python scripts/run_hot_engine_once.py --source integration_published --limit 50
```

输出目录：
- `out/hot_engine_queues/queue_review.md`
- `out/hot_engine_queues/source_research.md`
- `out/hot_engine_queues/monitor.md`
- `out/hot_engine_queues/reject.md`
- `out/hot_engine_queues/whale_digest.md`

## 模型运行模式（仅 mock / openrouter）

仅通过环境变量切换运行时（不要把任何 API Key 写入代码/文档/日志）。

1) mock（默认，不走网络）

```bash
$env:MODEL_RUNTIME="mock"
python scripts/test_llm_client_mock.py
```

2) openrouter（手动触发，只有你显式设置变量并运行才会请求外网）

```bash
$env:MODEL_RUNTIME="openrouter"
$env:OPENROUTER_API_KEY="你的 OpenRouter Key"
$env:OPENROUTER_MODEL="anthropic/claude-sonnet-4.6"
$env:MODEL_TIMEOUT_SECONDS="90"
python scripts/test_llm_client_openrouter.py
```

## 真实 Claude 单条生成测试（手动，不自动运行）

要求：
- 只跑 1 条（不要批量）
- 输出到 `out/generated_posts/`
- 不自动发布；后续仍走 `publish_from_generated.py --dry-run`

手动运行（PowerShell）：

```bash
$env:MODEL_RUNTIME="openrouter"
$env:OPENROUTER_API_KEY="你的OpenRouterKey"
$env:OPENROUTER_MODEL="anthropic/claude-sonnet-4.6"
python scripts/generate_from_queue.py --queue queue_review --limit 1 --runtime openrouter
```

生成后请先打开预览：
- `out/generated_posts/queue_review_drafts.md`
- `out/generated_posts/whale_digest_drafts.md`

发布阶段保持 dry-run：

```bash
python scripts/publish_from_generated.py --dry-run
```

## Legacy（保留但不作为主路线）

项目里仍保留 `evaluate_hot_input.py` / `generate_hot_draft.py` 等早期脚本用于旧 pipeline 兼容；但 Hot Engine 主路线以 `run_hot_engine_once.py` + 规则层为准。
