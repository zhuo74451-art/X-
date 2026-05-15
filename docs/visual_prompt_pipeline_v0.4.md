# visual_prompt_pipeline v0.4

## 1. 这套 pipeline 做什么

visual_prompt_pipeline 是 CoinMeta X Hot Follow Engine 的“视觉后半段”本地自动化入口：把你复制的一条帖子/素材，自动做成“可交给 image2 手动出图”的完整包（prompt + 审核页 + 可追溯来源），并输出到本地文件夹。

它解决的问题：
- 不再靠人工/ChatGPT 主脑来决定视觉路线、图上文字压缩、风险 guardrails
- 每次运行都有 run 目录，便于追溯、复盘和迭代规则
- 支持 override JSON：当运营审核觉得图上文字或路线不理想，可用同一份输入快速重跑，而不是手动改 prompt

## 2. 当前边界（v0.4）

严格边界：
- 不调用 OpenAI / OpenRouter / Claude / image2 / X API
- 不生成图片
- 不上传图片
- 不真实发帖
- 不处理任何 API Key

v0.4 只做：本地规则化 pipeline + 文件输出 + 人工审核页。

## 3. 输入方式

### 3.1 从剪贴板输入（推荐日常）

- PowerShell 入口：
  - `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_clipboard.ps1`
- 运行时会把剪贴板文本落盘到：
  - `data/visual_inbox/YYYYMMDD_HHMMSS_clipboard_input.txt`
- 然后自动运行 pipeline（input-type=auto）。

### 3.2 从文件输入

- PowerShell 入口：
  - `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_file.ps1 <input_file>`
  - 可选：强制 route 或 override：
    - `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_file.ps1 <input_file> D data/visual_inbox/my_override.json`
    - `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_file.ps1 <input_file> auto data/visual_inbox/my_override.json`

### 3.3 直接跑 Python

- `python scripts/visual/visual_prompt_pipeline.py --input-file <path> --input-type auto`
- 可选：
  - `--route A|B|C|D|E|F|G|H|I`
  - `--override-file data/visual_inbox/my_override.json`

参数行为：
- `--input-type auto`：自动识别 post/raw/mixed
- `--route`：人工强制路线（route_decision 会标记 forced_route）
- `--override-file`：人工覆盖 route/标题/副标题/blocks/footer（并标记 override_applied）
- 未知参数必须报错（argparse allow_abbrev=false）。

## 4. 输出文件说明

每次运行生成一个 run 目录：
- `out/visual_pipeline/YYYYMMDD_HHMMSS_<short_slug>/`

目录内文件：
- input_raw.txt：原始输入文本（不可逆追溯源）
- input_normalized.json：输入类型识别结果 + 分段（主帖/首评）+ override 文件路径
- extracted_facts.json：规则抽取出的实体/关键词/数字/法律词等
- route_decision.json：路线打分/原因；包含 forced_route/override_applied 等标记
- image_text_pack.json：图上文字承载结构（title/subtitle/blocks/footer）+ source_trace + override_applied
- prompt_pack.json：选用模板后生成的 prompt variants（render_safe + standard）+ negative_prompt + guardrails
- validation_checklist.json：人工审图 checklist（text_check/visual_check/risk_check）
- audit_report.md：全量审计报告（偏调试）
- operator_review.md：运营审核页（简洁版）
- ready_to_generate_prompt.md：可直接复制给 image2 的 prompt（不出图）

全局最新指针：
- `out/visual_pipeline/latest_run.json`
  - 包含 run_dir / operator_review / ready_to_generate_prompt / audit_report / check_status

## 5. 日常使用流程（概览）

建议顺序：
1. 从剪贴板或文件运行（生成 run 目录）
2. 打开 latest_run.json，找到 operator_review.md
3. 在 operator_review 中检查：路线、图上三模块文字、风险 guardrails、source_trace
4. 满意：复制 ready_to_generate_prompt.md 到 image2（手动出图）
5. 不满意：走 override 修正流程（下一节）。

## 6. override 修正流程

### 6.1 生成 override 草稿

- `python scripts/visual/create_override_from_latest.py`
- 会读取：
  - `out/visual_pipeline/latest_run.json`
  - 对应 run 里的 `image_text_pack.json`
- 输出：
  - `data/visual_inbox/YYYYMMDD_HHMMSS_override_from_latest.json`

### 6.2 编辑 override 文件

修改你想覆盖的字段即可（未填写的字段保留自动结果）：
- route（可选）：强制路线
- title / subtitle（可选）
- blocks（可选）：最多 3 个 block；每个 block 可填 label/line_1/line_2/line_3
- footer（可选）
- notes（可选）：写人工修改原因

注意：
- 不要写入任何敏感 token / API Key
- 不要编造不存在的数据（只优化表达与排版）。

### 6.3 使用 override 重跑

- 文件入口：
  - `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_file.ps1 <input_file> auto data/visual_inbox/my_override.json`
- 或 Python：
  - `python scripts/visual/visual_prompt_pipeline.py --input-file <input_file> --input-type auto --override-file data/visual_inbox/my_override.json`

产物变化：
- route_decision.json 会标记 override_applied/override_file
- image_text_pack.json 会标记 override_applied/override_notes，并使用 override 覆盖的文字
- operator_review.md 会显示 override_applied 与 override_file。

## 7. 样本测试命令

### 7.1 样本一键

- `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_pipeline_sample.ps1 musk`
- `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_pipeline_sample.ps1 whale`

成功输出：
- `VISUAL_PIPELINE_SAMPLE_PASS`

### 7.2 文件入口

- `powershell -ExecutionPolicy Bypass -File scripts/visual/run_visual_from_file.ps1 data/samples/visual_input_daily_whale_digest_post.txt`

成功输出：
- `VISUAL_PIPELINE_FILE_PASS`

### 7.3 override 草稿

- `python scripts/visual/create_override_from_latest.py`

成功输出：
- `OVERRIDE_DRAFT_CREATED: data/visual_inbox/..._override_from_latest.json`

## 8. 常见问题

### 8.1 终端里中文乱码

有时 PowerShell/终端显示会乱码，但文件本身是 UTF-8。建议直接在 IDE 打开文件查看内容。

### 8.2 latest_run.json 解析报 Unexpected UTF-8 BOM

create_override_from_latest.py 已使用 utf-8-sig 兼容读取 BOM。

### 8.3 看到 “undefined”

本项目脚本对未知参数使用 argparse 严格报错，不会吞掉 undefined。若日志里出现 undefined，优先怀疑是外部执行器拼接参数；可用 “unknown args” 验证命令立刻失败。

## 9. 下一阶段 v0.5 计划（不在 v0.4 实现）

方向（仅计划）：
- 路线模板扩展：B/G/H 等更多骨架模板
- 更强的 line width audit 与自动收缩策略（仍保留原文追溯）
- 规则配置外置（JSON config）与权重可调
- 输出汇总页（多 run 对比）与“失败原因统计”
