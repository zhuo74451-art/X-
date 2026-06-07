# CoinMeta X Hot Follow Engine v0.1.0

**X/Twitter 半自动内容运营 Demo 系统**

从本地候选内容、热点、快讯或监控数据中生成可人工审核的 X 内容草稿与运营辅助报告。

---

## ⚠️ 重要声明

**当前版本 v0.1.0 只做本地 Demo：**

- ✅ 本地 dry-run
- ✅ 候选内容导入
- ✅ 评分/筛选
- ✅ 推文草稿生成
- ✅ 运营节奏模拟
- ✅ 预览/报告输出
- ❌ **不自动发布**
- ❌ **不接真实 X API**
- ❌ **不启动后台任务/daemon/cron**
- ❌ **不调用付费模型**
- ❌ **不真实发帖**

如需启用真实发布或模型调用，必须经过单独审批和配置。详见 [NO_AUTO_PUBLISH_POLICY.md](docs/NO_AUTO_PUBLISH_POLICY.md)。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 本地 dry-run | 全流程模拟，不触网 |
| 候选内容导入 | 从 Integration API / 本地数据导入候选热点 |
| 评分/筛选 | 规则引擎评分、风险分级、队列分流 |
| 推文草稿生成 | mock 或 OpenRouter 生成中文 X 推文草稿 |
| 运营节奏模拟 | 队列管理、发布节奏、审核流程模拟 |
| 预览/报告输出 | Markdown/JSON 报告，可本地浏览器打开 |
| 安全闸门 | autopublish_guard 多层安全检查 |
| 不自动发布 | 默认一切 generating 和 publishing 均为 dry-run |

---

## 项目结构

```
.
├── README.md                          # 本文件
├── CLAUDE.md                          # Claude Code 执行规范
├── config.yaml                        # 项目配置
├── .env.example                       # 环境变量模板
├── requirements.txt                   # Python 依赖
├── docs/                              # 文档
│   ├── DEPLOYMENT.md                  # 部署指南
│   ├── SECURITY_AND_ENV.md            # 安全与环境变量
│   ├── DEMO_RUN_GUIDE.md              # Demo 运行指南
│   ├── PORTABLE_RELEASE_MANIFEST.md   # 便携发布清单
│   └── NO_AUTO_PUBLISH_POLICY.md      # 禁止自动发布策略
├── scripts/                           # 所有脚本
│   ├── run_pipeline_once.py           # 一键 pipeline
│   ├── run_autopublish_dryrun_once.py # 自动发布 dry-run
│   ├── run_hot_engine_once.py         # Hot Engine 主入口
│   ├── init_db.py                     # 初始化数据库
│   ├── import_sample_hot_inputs.py    # 导入样本数据
│   ├── evaluate_hot_input.py          # 评分引擎
│   ├── generate_hot_draft.py          # 草稿生成（旧版）
│   ├── generate_from_queue.py         # 草稿生成（新版）
│   ├── export_review_queue.py         # 导出审核队列
│   ├── publish_from_generated.py      # 发布（dry-run）
│   ├── autopublish_guard.py           # 安全闸门
│   ├── llm_client.py                  # LLM 客户端
│   ├── check_x_publish_config.py      # 发布配置检查
│   └── run_v001_portable_release_check.py  # 发布检查
├── reports/                           # 报告输出
├── demo_outputs/                      # Demo 静态页面
├── out/                               # 运行时输出
├── data/                              # 数据文件
├── prompts/                           # 提示词模板
├── configs/                           # 配置文件
└── .gitignore                         # Git 忽略规则
```

---

## 快速开始（本地 Demo）

### 前置条件

- Python 3.9+
- Git

### 安装和运行

```bash
# Clone 仓库
git clone https://github.com/zhuo74451-art/X-.git
cd X-

# 安装依赖（当前仅标准库，无需 pip install）
# 如果未来加了第三方依赖：
# pip install -r requirements.txt

# 运行本地 dry-run
python scripts/run_pipeline_once.py

# 运行自动发布 dry-run
python scripts/run_autopublish_dryrun_once.py --limit 50

# 运行便携发布检查
python scripts/run_v001_portable_release_check.py
```

### 输出预览

```bash
# 查看审核队列
cat out/x_review_queue.md

# 查看草稿
cat out/generated_posts/queue_review_drafts.md

# 查看 dry-run 发布日志
cat out/publish_logs/dryrun_posts.jsonl
```

### 打开 Demo 首页

用浏览器打开：

```
demo_outputs/v001_portable_release_index.html
```

---

## 环境变量

所有环境变量默认安全关闭。详见 `.env.example`。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODEL_RUNTIME` | `mock` | 模型运行模式：mock / openrouter |
| `ENABLE_X_POST` | `false` | 禁止真实 X 发帖 |
| `ENABLE_AUTO_PUBLISH` | `false` | 禁止自动发布 |
| `ENABLE_MODEL_CALL` | `false` | 禁止调用付费模型 |
| `ENABLE_DAEMON` | `false` | 禁止后台进程 |
| `DRY_RUN` | `true` | 全局 dry-run |

---

## 模型运行模式

### Mock 模式（默认，安全）

```bash
# 默认就是 mock，不走网络
python scripts/test_llm_client_mock.py
```

### OpenRouter 模式（手动触发，需显式设置 Key）

```bash
export MODEL_RUNTIME="openrouter"
export OPENROUTER_API_KEY="你的 Key"
export OPENROUTER_MODEL="anthropic/claude-sonnet-4.6"
python scripts/test_llm_client_openrouter.py
```

---

## 流量信号源

- `@trumpchinese1`：仅作为 traffic_signal（不是 fact_source），命中后必须二次核查英文一手来源或可靠媒体；不进入 auto_publish / direct citation。

---

## 当前架构（统一路线）

```
Hot Engine（规则层）
    ↓
Rulebook / Event Cluster / Queue Split
    ↓
Skill Prompt → OpenRouter → Claude → 官号 X 输出
```

---

## 安全原则

1. **不提交** `.env`、API Key、Token、Cookie、浏览器缓存
2. **默认** 所有发布动作为 dry-run
3. **默认** 不启动后台循环/daemon/cron
4. 所有 `publish/send/post/upload` 需显式审批
5. 历史报告中的绝对路径为历史遗留，不影响当前运行

详见：
- [SECURITY_AND_ENV.md](docs/SECURITY_AND_ENV.md)
- [NO_AUTO_PUBLISH_POLICY.md](docs/NO_AUTO_PUBLISH_POLICY.md)

---

## 部署与迁移

详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

---

## License

本项目为 CoinMeta 内部 Demo 系统。对外发布前需确认 License。
