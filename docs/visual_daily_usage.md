# 日常使用

## 方式一：剪贴板（推荐）

1. 复制帖子或素材文本到剪贴板
2. 运行：
   - `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_clipboard.ps1`
3. 打开：
   - `out/visual_pipeline/latest_run.json`
4. 找到并打开：
   - `operator_review` 指向的 `operator_review.md`
5. 检查：
   - 路线是否合理（selected_route / forced_route / override_applied）
   - 图上三模块文字是否自然、是否过长、是否有误导风险
   - Risk Flags / Guardrails 是否合理
   - Source Trace 是否能追溯到原文
6. 满意则：
   - 打开 `ready_to_generate_prompt` 指向的 `ready_to_generate_prompt.md`
   - 复制内容到 image2（手动出图）
7. 不满意则：
   - 运行：`python scripts/visual/create_override_from_latest.py`
   - 去 `data/visual_inbox/` 找到新生成的 override 草稿，编辑后重跑（见“override 修正”）

## 方式二：文件输入

1. 把文本保存为 .txt 放到：
   - `data/visual_inbox/`
2. 运行：
   - `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_file.ps1 data/visual_inbox/my_post.txt`
3. 打开 latest_run.json → operator_review → ready_to_generate_prompt（流程同上）

## override 修正（人工改图上文字/路线）

### A. 从 latest 自动生成 override 草稿

- `python scripts/visual/create_override_from_latest.py`

输出：
- `data/visual_inbox/YYYYMMDD_HHMMSS_override_from_latest.json`

### B. 编辑 override 文件

只改你想覆盖的字段：
- route（可选）
- title / subtitle（可选）
- blocks（可选）
- footer（可选）
- notes（可选）

### C. 带 override 重跑

如果只想传 override，不强制 route：
- `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_file.ps1 data/visual_inbox/my_post.txt auto data/visual_inbox/my_override.json`

如果同时强制 route：
- `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_file.ps1 data/visual_inbox/my_post.txt D data/visual_inbox/my_override.json`

## 你每天只需要记住的三条命令

1. 剪贴板一键跑：
   - `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_clipboard.ps1`
2. 生成 override 草稿：
   - `python scripts/visual/create_override_from_latest.py`
3. 文件输入重跑（带 override）：
   - `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_file.ps1 data/visual_inbox/my_post.txt auto data/visual_inbox/my_override.json`

## 边界提醒

- pipeline 不会调用任何外部 API
- pipeline 不会生成图片
- 最终出图仍然是你手动把 ready_to_generate_prompt.md 复制到 image2
- 不要在 data/visual_inbox/ 放 API Key 或敏感 token
