# CoinMeta X Hot Follow Engine｜执行规范

## 项目定位

本项目是 CoinMeta / 币界网中文 X 热点跟随系统。

当前阶段是 v0.1-v0.2 过渡：
先跑通文本内容闭环，再逐步接入 Claude、Humanize、记忆、图像与 LangGraph。

## 分工

老板：
提供业务判断、素材、最终拍板。

GPT 总架构师：
负责路线、提示词、模板、验收标准。

Trae / Claude Code：
只负责工程执行，不自行设计 Prompt。

Claude 模型：
负责高质量中文创作、角度提炼、用户影响翻译。

## 关键规则

1. Prompt 由 GPT 总架构师提供，执行器不得自行创作或扩写。
2. API Key 不得写入任何文件、日志、README 或样本。
3. OpenRouter Key 只能由老板在 PowerShell 当前窗口设置。
4. 默认不要跑真实模型，除非明确要求。
5. 所有真实模型测试必须使用 MAX_ITEMS_PER_RUN 限量。
6. 当前不接真实 X，不自动发帖。
7. 当前不接 LangGraph / Mem0 / GraphRAG / Image2，除非进入对应阶段。
8. 每次改动必须说明修改文件、运行命令、输出结果和是否有报错。
9. 遇到问题先分层排查：环境层、调用层、解析层、业务层、内容层。
10. 不要把模型输出问题全都当成 Prompt 问题。

## 当前推荐流程

hot_inputs
↓
evaluate_hot_input
↓
generate_hot_draft
↓
export_review_queue
↓
人工验收

后续再加：

humanize_draft
style_memory
fact_pack
image_generation
LangGraph

## 指令执行纪律

每次任务必须明确：

- 阶段名称
- 目标
- 允许修改文件
- 禁止修改文件
- 是否允许跑真实模型
- 验收命令
- 返回内容
