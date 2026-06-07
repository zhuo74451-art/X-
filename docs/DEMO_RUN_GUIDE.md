# X Automation v0.1.0 Demo 运行指南

## 目标

在本地运行完整的 X 内容运营 Demo 流程，不触网、不发帖、不调模型。

---

## 第一步：初始化

```bash
# 在项目根目录执行
cd X-

# 初始化数据库
python scripts/init_db.py

# 导入样本数据
python scripts/import_sample_hot_inputs.py
```

---

## 第二步：运行 Pipeline

### 方式 A：一键 Pipeline

```bash
python scripts/run_pipeline_once.py
```

这会依次执行：
1. init_db
2. import_sample_hot_inputs
3. evaluate_hot_input（规则评分）
4. generate_hot_draft（mock 生成草稿）
5. export_review_queue（导出审核队列）

### 方式 B：完整 Dry-Run（含发布模拟）

```bash
python scripts/run_autopublish_dryrun_once.py --limit 50
```

这会额外执行：
- Hot Engine 事件分流
- 队列生成
- 发布 dry-run 模拟
- 输出 dry-run 日志

---

## 第三步：查看输出

### 审核队列

```bash
cat out/x_review_queue.md
```

### 生成草稿

```bash
cat out/generated_posts/queue_review_drafts.md
cat out/generated_posts/whale_digest_drafts.md
```

### Dry-Run 发布日志

```bash
cat out/publish_logs/dryrun_posts.jsonl
```

### Hot Engine 队列

```bash
cat out/hot_engine_queues/queue_review.md
cat out/hot_engine_queues/source_research.md
cat out/hot_engine_queues/monitor.md
cat out/hot_engine_queues/reject.md
cat out/hot_engine_queues/whale_digest.md
```

---

## 第四步：打开 Demo 首页

用浏览器打开：

```
demo_outputs/v001_portable_release_index.html
```

---

## 第五步：运行发布检查

```bash
python scripts/run_v001_portable_release_check.py
```

确认所有检查项通过。结果在：
- `reports/v001_portable_release_check.json`
- `reports/v001_portable_release_check.md`

---

## 可选：更多 Demo 操作

### Hot Engine 离线运行（无网络）

```bash
python scripts/run_hot_engine_offline_once.py
```

### 测试套件

```bash
# 规划测试
python scripts/run_x_v2_001_planning_tests.py

# 硬闸门测试
python scripts/run_x_v2_002_hard_gates.py

# AI 内容审查测试
python scripts/run_x_v2_003_ai_content_review_tests.py

# 重写与审查测试
python scripts/run_x_v2_004_tests.py

# 多角色生成测试
python scripts/run_x_v2_005_tests.py

# 真实事件包测试
python scripts/run_x_v2_006_tests.py

# 受众改写测试
python scripts/run_x_v2_008_audience_context_tests.py

# 中文锐度测试
python scripts/run_x_v2_008_chinese_sharp_audience_tests.py

# 测试账号发布测试
python scripts/run_x_v2_009_test_account_publisher_tests.py
```

---

## 确认安全

运行配置检查：

```bash
python scripts/check_x_publish_config.py
```

预期输出确认所有发布开关为 `false`：

```
- AUTO_PUBLISH_ENABLED: false
- AUTO_PUBLISH_DRY_RUN: true
- ok: false
```

这是**正常且安全**的状态。

---

## 故障排查

### 问题：找不到 `x_review_queue.md`

先运行 `python scripts/run_pipeline_once.py` 生成输出文件。

### 问题：数据库错误

删除 `hot_follow.db` 后重新运行 `python scripts/init_db.py`。

### 问题：Mock 模式生成空内容

Mock 模式使用预设的模拟数据。检查 `scripts/llm_client.py` 中的 mock 逻辑，确认 `MODEL_RUNTIME` 未设为 `openrouter`。
