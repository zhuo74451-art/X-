# Source Filter QA Checklist（@trumpchinese1 / external_signal_source）

目标：独立验证 @trumpchinese1（external_signal_source）不会被误接入主生产链路；不会被当作 fact_source；internal_db 仍为第一版优先；视觉 pipeline 不被外部源逻辑污染；auto_publish 不会被打开。

约束（QA 执行侧）：
- 不调用外部 API
- 不生成图片
- 不 push GitHub

## Source Filter QA Checklist

- 账号定位与边界
  - @trumpchinese1 仅作为 traffic_signal（线索/流量信号），不是事实源
  - needs_verification 必须为 true
  - publish_as_source 必须为 false
  - allowed 也不得进入：content_generation / visual_generation / auto_publish / fact_source / direct_quote
- 生产链路隔离
  - 项目内不得存在“抓取 @trumpchinese1 并入库到主输入表”的生产脚本/定时器
  - @trumpchinese1 不得出现在任何 trusted / fact_source / source_registry（权威新闻源）名单中
  - traffic_signal 不得被当作事实锚点（fact_anchor）或事实来源字段写入正文引用映射
- 优先级与路由
  - 第一版 internal_db 仍为主链路输入；external_signal_source 仅用于触发核查/监控
  - source-level filter（blocked）必须优先于热度/评分（hot_score/hotness_score 等）：blocked 直接阻断进入 hot_engine / content_generation / visual_generation / auto_publish
- 视觉管线隔离
  - visual_prompt_pipeline 不应引入 external/integration 抓取逻辑
  - 视觉回归样本跑通，且输出为 dry_run（只生成 prompt/审核材料，不生成图片）
- 自动发布护栏
  - AUTO_PUBLISH_DRY_RUN 默认 true
  - AUTO_PUBLISH_ENABLED 默认 false
  - 即便上游产出 publish_mode=auto_publish，也应降级为 queue_review

## 4 个样本预期（按当前实现）

样本 1：AI policy（allowed）
- 期望：source_filter_status=allowed
- 期望：source_role=traffic_signal
- 期望：needs_verification=true
- 期望：publish_as_source=false
- 期望：blocked_use 至少包含 content_generation / visual_generation / auto_publish / fact_source / direct_quote

样本 2：中国敏感政治（blocked）
- 期望：source_filter_status=blocked
- 期望：block_reason 包含 source_sensitive_filter:cn_politics_sensitive
- 期望：blocked_use 包含 hot_engine / content_generation / visual_generation / auto_publish / fact_source / direct_quote

样本 3：drugs（blocked）
- 期望：source_filter_status=blocked
- 期望：block_reason 包含 source_sensitive_filter:drugs

样本 4：gambling（blocked）
- 期望：source_filter_status=blocked
- 期望：block_reason 包含 source_sensitive_filter:gambling

注意：
- data/samples/source_filter_trumpchinese1_cn_sensitive_blocked.txt 当前写的是 block_reason_contains: cn_sensitive_politics，但 configs/source_filters/source_sensitive_filter.json 中类别名为 cn_politics_sensitive；以脚本实际输出为准做验收。

## 手动验收命令

Source filter（PowerShell 下 handle 需要加引号）：

```powershell
python scripts/hot_engine/check_source_filter.py --source-id x_trumpchinese1 --handle '@trumpchinese1' --text "特朗普总统：我们在人工智能领域遥遥领先。"
python scripts/hot_engine/check_source_filter.py --source-id x_trumpchinese1 --handle '@trumpchinese1' --text "这是一条测试样本，文本包含习近平，用于验证中国国内敏感政治过滤。"
python scripts/hot_engine/check_source_filter.py --source-id x_trumpchinese1 --handle '@trumpchinese1' --text "这是一条测试样本，文本包含芬太尼 fentanyl，用于验证毒品相关过滤。"
python scripts/hot_engine/check_source_filter.py --source-id x_trumpchinese1 --handle '@trumpchinese1' --text "这是一条测试样本，文本包含博彩、赌博、赌场，用于验证博彩过滤。"
```

Auto publish 配置护栏检查：

```powershell
python scripts/check_x_publish_config.py
```

视觉回归（只生成 prompt/审计材料，不生成图片）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_pipeline_sample.ps1 musk
powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_pipeline_sample.ps1 whale
python scripts/visual/check_visual_style_profiles.py
```

## 风险点

- 术语漂移：文档/样本中的 cn_sensitive_politics 与实现中的 cn_politics_sensitive 不一致，容易导致回归脚本或人工验收误判。
- 误接入主链路：未来若新增 external_signal_db 抓取/同步脚本，必须显式隔离与默认禁用（不允许进入 auto_publish / 引用 / 事实锚点）。
- 事实锚点误用：如将 traffic_signal 的文本当作事实依据写入“来源/证据链”，会导致内容风险升级。
- Auto publish 被误打开：需要同时满足 DRY_RUN=false 与 ENABLED=true 才会真正发推；任何自动化环境变量变更都应走审批与审计。

## 回归项目（每次改动必跑）

- Source filter：4 个样本（allowed + 3 blocked）
- 发布护栏：check_x_publish_config.py（确认默认禁用）
- 视觉：run_visual_pipeline_sample.ps1（musk/whale）+ check_visual_style_profiles.py
