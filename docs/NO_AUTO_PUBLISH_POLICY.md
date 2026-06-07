# X Automation v0.1.0 禁止自动发布策略

## 原则

本项目是 **Demo 系统**，不是生产发布系统。

---

## 允许的操作

| 操作 | 状态 |
|------|------|
| 生成草稿 | ✅ 允许 |
| 生成预览 | ✅ 允许 |
| 生成运营计划 | ✅ 允许 |
| 生成报告 | ✅ 允许 |
| 评分/筛选 | ✅ 允许 |
| 本地 dry-run | ✅ 允许 |
| 创建审核队列 | ✅ 允许 |

## 禁止的操作

| 操作 | 状态 |
|------|------|
| 真实发帖到 X | ❌ 禁止 |
| 自动发帖到 X | ❌ 禁止 |
| 定时循环发帖 | ❌ 禁止 |
| 生产环境写入 | ❌ 禁止 |
| 未经审批的 publish/send/post/upload | ❌ 禁止 |
| 后台 daemon/cron 自动运行 | ❌ 禁止 |

---

## 安全闸门

项目内置 `autopublish_guard.py`，在执行任何 publish 动作前检查：

1. `AUTO_PUBLISH_ENABLED` 是否为 `true`
2. `DRY_RUN` 是否为 `true`
3. 是否存在真实的 X API 凭证
4. 内容是否通过风险评估

默认情况下，闸门会 **block 所有 publish 动作**。

### 验证闸门状态

```bash
python scripts/check_x_publish_config.py
```

预期输出：
```
[check_x_publish_config] X publish env check (no network, no post)
- AUTO_PUBLISH_ENABLED: false
- AUTO_PUBLISH_DRY_RUN: true
- ok: false
- missing: X_API_KEY,X_API_SECRET,X_ACCESS_TOKEN,X_ACCESS_TOKEN_SECRET
```

这是**正常且安全的**输出。

---

## 如需启用发布

必须经过以下**审批流程**：

1. 用户明确表示要启用真实发布
2. 确认理解风险：
   - 发帖内容公开可见
   - 发帖不可撤销
   - 可能触发 X 平台风控
3. 配置真实 X API 凭证
4. 单独设置 `ENABLE_X_POST=true`
5. 单次运行，完成后恢复安全设置

步骤见 [SECURITY_AND_ENV.md](SECURITY_AND_ENV.md)。

---

## 开发者须知

- 新增功能时，如果涉及 publish/send/post/upload，必须经过 `autopublish_guard` 检查
- 不要在脚本中绕过安全闸门
- 不要在测试中自动设置 `ENABLE_X_POST=true`
- 不要创建 cron/systemd/daemon 配置
- CI/CD 中永远设置 `DRY_RUN=true`
