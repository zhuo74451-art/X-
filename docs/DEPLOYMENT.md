# X Automation v0.1.0 部署指南

## 适用环境

- Windows（PowerShell）
- Linux / macOS（bash）
- Python 3.9+

---

## 1. Clone 仓库

### Windows PowerShell

```powershell
git clone https://github.com/zhuo74451-art/X-.git
cd X-
```

### Linux / macOS

```bash
git clone https://github.com/zhuo74451-art/X-.git
cd X-
```

---

## 2. Checkout Tag（推荐）

```bash
git checkout x-automation-v0.1.0
```

查看可用 tags：

```bash
git tag -l
```

---

## 3. 安装依赖

当前 v0.1.0 版本只使用 Python 标准库，无需安装第三方依赖。

```bash
# 检查 Python 版本
python --version
# 要求 >= 3.9
```

如果后续版本添加了第三方依赖：

```bash
python -m pip install -r requirements.txt
```

---

## 4. 运行本地 Dry-Run

### 一键 Pipeline（推荐）

```bash
python scripts/run_pipeline_once.py
```

### 自动发布 Dry-Run（完整流程）

```bash
python scripts/run_autopublish_dryrun_once.py --limit 50
```

### Hot Engine 单独运行

```bash
python scripts/run_hot_engine_once.py --source integration_published --limit 50
```

---

## 5. 打开预览/报告

### 查看 Markdown 报告

```bash
cat out/x_review_queue.md
cat out/generated_posts/queue_review_drafts.md
cat out/publish_logs/dryrun_posts.jsonl
```

### 浏览器打开 Demo 首页

**Windows：**

```powershell
start demo_outputs/v001_portable_release_index.html
```

**Linux / macOS：**

```bash
xdg-open demo_outputs/v001_portable_release_index.html
# 或
open demo_outputs/v001_portable_release_index.html
```

---

## 6. 部署静态 HTML 报告

所有报告位于 `reports/` 和 `demo_outputs/`，可直接复制到任意静态服务器：

```bash
# 复制 demo 文件到 web 目录
cp -r demo_outputs/* /var/www/html/x-automation-demo/
```

无需后端服务，纯静态页面即可浏览。

---

## 7. 运行便携发布检查

```bash
python scripts/run_v001_portable_release_check.py
```

通过后会在 `reports/` 产出：
- `v001_portable_release_check.json`
- `v001_portable_release_check.md`

---

## 8. 后续如需接真实 X API（需单独审批）

当前版本不包含真实 X 发布功能。如需启用：

1. **必须获得明确授权**
2. 创建 `.env` 文件（从 `.env.example` 复制）
3. 填入真实的 X API Key / Access Token
4. 将以下开关设为 `true`：
   - `ENABLE_X_POST=true`
   - `ENABLE_AUTO_PUBLISH=true`
5. 确认理解风险后再运行

⚠️ **警告**：设置 `ENABLE_X_POST=true` 后会真实发帖到 X/Twitter，无法撤销。

---

## 9. 后续如需 Daemon/Cron（需单独审批）

当前版本不创建任何后台任务。如需定时运行：

1. **必须获得明确授权**
2. 使用操作系统级的 cron（Linux）或 Task Scheduler（Windows）
3. 不要在项目内创建 systemd service 或 daemon 脚本
4. 确保每次运行前检查 `DRY_RUN=true`

---

## 常见问题

### Q: 运行报错 `ModuleNotFoundError`

A: bash
# 确认在项目根目录运行
cd X-
python scripts/run_pipeline_once.py


### Q: `FileNotFoundError` 或找不到输出文件

A: bash
# 先初始化数据库
python scripts/init_db.py
# 再导入样本数据
python scripts/import_sample_hot_inputs.py


### Q: 如何确认不会真实发帖？

A: bash
python scripts/check_x_publish_config.py
# 应输出: AUTO_PUBLISH_ENABLED: false


### Q: 模型调用会扣费吗？

A: 默认 `MODEL_RUNTIME=mock`，不会调用任何模型 API。只有显式设置 `MODEL_RUNTIME=openrouter` 并配置 Key 后才会请求外部 API。

### Q: 在哪里改配置？

A: 环境变量通过 `.env` 或 shell export 设置，项目配置在 `config.yaml`。
