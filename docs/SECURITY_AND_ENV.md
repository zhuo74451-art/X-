# X Automation v0.1.0 安全与环境变量

## 核心安全原则

### 绝对不提交

以下内容**永远不会**出现在 Git 仓库中（已在 `.gitignore` 中配置）：

| 类别 | 示例 | Git 状态 |
|------|------|----------|
| `.env` 真实文件 | `.env`, `.env.production` | ✅ 已忽略 |
| X API Key | `X_API_KEY`, `X_API_SECRET` | ✅ 已忽略 |
| X Access Token | `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` | ✅ 已忽略 |
| OpenRouter Key | `OPENROUTER_API_KEY` | ✅ 已忽略 |
| OpenAI Key | `OPENAI_API_KEY` | ✅ 已忽略 |
| Cookie/Session | `auth.json`, `auth.lock` | ✅ 已忽略 |
| 浏览器缓存 | `*.cache`, `.vscode/` | ✅ 已忽略 |
| 数据库文件 | `*.db` | ✅ 已忽略 |
| 密钥文件 | `*.key`, `*.pem`, `*.secret`, `*.token` | ✅ 已忽略 |

### 默认安全开关

| 开关 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_X_POST` | `false` | 禁止真实 X 发帖 |
| `ENABLE_AUTO_PUBLISH` | `false` | 禁止自动发布 |
| `ENABLE_MODEL_CALL` | `false` | 禁止调用付费模型 |
| `ENABLE_DAEMON` | `false` | 禁止后台进程 |
| `DRY_RUN` | `true` | 全局 dry-run |

所有发布动作默认关闭，所有后台循环默认关闭。

---

## 环境变量配置

### 使用 .env.example 模板

项目提供 `.env.example` 作为模板，其中**全部使用占位符**：

```bash
# 复制模板
cp .env.example .env

# 编辑 .env 填入真实值（不会被 git 跟踪）
```

### 完整变量列表

```bash
# X API（仅当用户明确批准真实发帖时才填写）
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_SECRET=

# 模型 API Key（仅当用户明确批准模型调用时才填写）
OPENROUTER_API_KEY=
OPENAI_API_KEY=

# 安全开关（默认全部关闭）
ENABLE_X_POST=false
ENABLE_AUTO_PUBLISH=false
ENABLE_MODEL_CALL=false
ENABLE_DAEMON=false
DRY_RUN=true
```

### 模型运行时

```bash
# Mock 模式（默认，不走网络，安全）
MODEL_RUNTIME=mock

# OpenRouter 模式（需显式设置，会请求外部 API）
MODEL_RUNTIME=openrouter
OPENROUTER_API_KEY=你的Key
OPENROUTER_MODEL=anthropic/claude-sonnet-4.6
MODEL_TIMEOUT_SECONDS=90
```

---

## 安全检查清单

部署前确认：

- [ ] `.env` 不会出现在 `git status` 中
- [ ] `.env.example` 中只含占位符，无真实值
- [ ] `.gitignore` 已覆盖所有敏感文件类型
- [ ] `ENABLE_X_POST=false`
- [ ] `ENABLE_AUTO_PUBLISH=false`
- [ ] `ENABLE_MODEL_CALL=false`
- [ ] `ENABLE_DAEMON=false`
- [ ] `DRY_RUN=true`
- [ ] 代码中无硬编码 Key/Token
- [ ] 日志中无 Key/Token 泄露

运行自动检查：

```bash
python scripts/run_v001_portable_release_check.py
```

---

## 如需启用模型或 X API

必须**按顺序**完成以下步骤：

1. 获得明确的用户书面/口头授权
2. 从 `.env.example` 复制创建 `.env`
3. 填入真实的 API Key/Token
4. 将对应开关设为 `true`
5. 确认理解风险（调用外部 API 可能产生费用，发帖不可撤销）
6. 运行一次，观察输出
7. 用完后将开关恢复为 `false` 或删除 `.env`

**永远不要**：
- 将含真实 Key 的 `.env` 提交到 Git
- 在代码中硬编码 Key/Token
- 在日志/报告中打印 Key/Token
- 未经审批开启自动发布
