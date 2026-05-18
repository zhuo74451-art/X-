# Image2 Generation Usage (v0.1)

本页用于 CoinMeta 视觉后处理：从 visual_prompt_pipeline 的 `ready_to_generate_prompt.md` 出发，生成图片落盘到本地运行目录。

## 定位

- 这是 ready_prompt 后处理工具，不接入 Hot Engine 主流程
- 不接入 X 发布链路，不自动发帖
- 默认 mock：不真实调用 OpenAI Image API
- Trae 不处理 OPENAI_API_KEY

## 输入与输出

**输入（二选一）**
- `--run-dir out/visual_pipeline/<run_id>`
- `--prompt-file out/visual_pipeline/<run_id>/ready_to_generate_prompt.md`

**输出目录**
- `out/visual_pipeline/<run_id>/generated_images/`
  - `image_generation_request.json`
  - `image_generation_mock_report.md`（mock）
  - `image_generation_report.md`（openai_image）
  - `image_001.png`（openai_image）
  - `image_001_meta.json`（openai_image）

## Mock（默认）

默认参数：
- `IMAGE_PROVIDER=mock`
- `IMAGE_MODEL=gpt-image-1`
- `IMAGE_SIZE=1024x1536`
- `IMAGE_QUALITY=medium`
- `IMAGE_N=1`

命令示例：

```bash
python scripts/visual/image2_generate_from_prompt.py --run-dir out/visual_pipeline/<run_id> --provider mock
```

说明：
- mock 模式只会生成 request/report，不会生成真实图片

## 手动 ChatGPT image2 出图流程

- 打开 `out/visual_pipeline/<run_id>/ready_to_generate_prompt.md`
- 复制其中的最终 prompt（render_safe 版本）
- 粘贴到你使用的 image2/GPT Image 工具中生成
- 将成图手动保存回 `out/visual_pipeline/<run_id>/generated_images/`（建议命名 `image_001.png`）
- 可手动补写 `image_001_meta.json`（记录来源、模型、尺寸、时间）

## API 自动出图流程（需用户手动配置）

启用条件：
- 必须显式设置 `--provider openai_image` 或 `IMAGE_PROVIDER=openai_image`
- 必须设置 `OPENAI_API_KEY`
- 如果缺少 `OPENAI_API_KEY`，脚本会清晰报错退出，不会 fallback mock

PowerShell 示例（仅示例，不由 Trae 执行）：

```powershell
$env:OPENAI_API_KEY="你的 key"
python scripts/visual/image2_generate_from_prompt.py --run-dir out/visual_pipeline/<run_id> --provider openai_image --quality medium --size 1024x1536
```

## 成本说明（估算）

以下为估算值，实际以 OpenAI 官方 pricing 为准：
- 1024x1536 low 约 $0.016 / 张
- 1024x1536 medium 约 $0.063 / 张
- 1024x1536 high 约 $0.25 / 张

## size / quality 选择建议

- X 4:5 主图：优先 `1024x1536`
- 日常测试：`quality=low/medium`
- 关键选题：`quality=medium/high`（建议先出 low 做构图验证，再升质量）

## 人工审图 checklist

- 中文是否清晰可读（尤其小字与数字）
- 是否出现乱码/错字/自动换行灾难
- 是否出现错误 Logo（交易所/公司/项目 logo 乱入）
- 是否误画真实公众人物肖像
- 是否有国旗对抗 / 政治宣传感
- 是否出现投资建议语气（买入/卖出/暴富/稳赚等）
- 是否符合 CoinMeta 官号风格（克制、财经媒体感、栏目感）
- 是否适合 X 4:5 信息流停留（第一眼是否能读懂标题与三模块）

## 安全边界

- 不自动发 X
- 不连接 Hot Engine 发布链路
- Trae 不处理 OPENAI_API_KEY
