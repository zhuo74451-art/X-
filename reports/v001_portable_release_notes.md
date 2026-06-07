# X Automation v0.1.0 — Portable Release Notes

**Release Date**: 2026-06-08  
**Tag**: `x-automation-v0.1.0`  
**GitHub**: https://github.com/zhuo74451-art/X-

---

## 当前版本包含什么

| 类别 | 内容 |
|------|------|
| **项目文档** | README.md, CLAUDE.md, 5 份 docs/ 文档 |
| **环境模板** | .env.example, requirements.txt, requirements-dev.txt |
| **发布检查** | run_v001_portable_release_check.py（20 项检查） |
| **Demo 入口** | v001_portable_release_index.html |
| **Hot Engine** | 规则引擎 + 队列分流 + 评分/筛选 |
| **草稿生成** | Mock 模式（默认）/ OpenRouter 模式（手动启用） |
| **发布模拟** | Dry-run 发布日志 + 审核队列 |
| **报告系统** | Markdown + JSON 双格式报告 |
| **安全闸门** | autopublish_guard 多层检查 |
| **历史报告** | v2-001 至 v2-009 全部测试与运行报告 |

## 当前版本不包含什么

| 类别 | 说明 |
|------|------|
| **真实 X 发帖** | 默认关闭，需单独审批 |
| **真实 X API 调用** | 不连接 Twitter API |
| **自动发布** | 不做 auto-publish |
| **后台循环** | 不创建 daemon/cron/systemd |
| **付费模型调用** | MODEL_RUNTIME 默认 mock |
| **浏览器自动化** | 不操作浏览器 |
| **图片生成** | 仅输出配图提示，不生成图片 |
| **Telegram/飞书** | 不接外部通知 |
| **LangGraph/Mem0** | 不接入 |
| **联网检索** | 不在当前阶段 |

## 安全边界

```
┌─────────────────────────────────────────────┐
│  生成草稿      ✅ 允许                        │
│  生成预览      ✅ 允许                        │
│  生成报告      ✅ 允许                        │
│  运营计划      ✅ 允许                        │
│  ─────────────────────────────               │
│  真实发帖      ❌ 禁止（需审批）               │
│  自动发帖      ❌ 禁止（需审批）               │
│  定时循环      ❌ 禁止（需审批）               │
│  生产写入      ❌ 禁止（需审批）               │
│  付费模型      ❌ 禁止（需审批）               │
│  后台服务      ❌ 禁止（需审批）               │
└─────────────────────────────────────────────┘
```

## 如何本地打开

1. 浏览器打开：`demo_outputs/v001_portable_release_index.html`
2. 查看报告：`reports/` 目录下所有 .md 和 .json 文件
3. 运行 Demo：`python scripts/run_pipeline_once.py`

## 如何迁移部署

详见 `docs/DEPLOYMENT.md`，简要步骤：

```bash
git clone https://github.com/zhuo74451-art/X-.git
cd X-
git checkout x-automation-v0.1.0
python scripts/run_pipeline_once.py
python scripts/run_v001_portable_release_check.py
```

## 后续如需真实发帖

必须经过以下**单独审批**：

1. **用户明确授权**：口头或书面确认要启用真实发布
2. **理解风险**：
   - 发帖内容公开可见且不可撤销
   - 可能触发 X 平台风控或限流
   - 模型调用产生费用
3. **配置凭证**：
   - 从 `.env.example` 创建 `.env`
   - 填入真实的 X API Key / Access Token
   - 如使用 OpenRouter，填入 API Key
4. **开启开关**：
   - `ENABLE_X_POST=true`
   - `ENABLE_AUTO_PUBLISH=true`（如需自动）
   - `ENABLE_MODEL_CALL=true`（如需模型）
   - `DRY_RUN=false`（关闭 dry-run）
5. **单次运行验证**：先跑 1 条确认正常
6. **用后恢复**：完成操作后将开关恢复为 `false`

**禁止在未审批状态下执行以上任何步骤。**

## 后续如需定时运行

1. 使用操作系统级 cron（Linux）或 Task Scheduler（Windows）
2. 不在项目内创建 daemon/systemd service
3. 确保每次执行前检查 `DRY_RUN=true`
4. 不要在无人值守状态下设置 `ENABLE_X_POST=true`

---

## 已知问题

- 历史报告 `reports/x_v2_002_hard_gate_report.md` 包含本机绝对路径（`C:\Users\zhuo7\...`），此为历史遗留记录，不影响运行
- Mock 模式生成的草稿为模板内容，不代表真实模型质量

## 致谢

本项目由 CoinMeta 团队驱动，Claude Code 辅助工程执行。
