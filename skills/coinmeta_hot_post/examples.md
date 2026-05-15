# Examples（bad vs good）

输入都是 event_pack（事件聚合包），不是单条快讯。重点：基于 best_source/缺口，写成可审核的官号草稿。

---

## 示例 1｜bad：把二手转述写成确定事实

### 输入（节选）

```json
{
  "event_cluster_id": "e_xxx",
  "cluster_title": "某交易所可能暂停提币",
  "cluster_queue": "queue_review",
  "risk_level": "high",
  "source_urls": ["https://t.me/example/1"],
  "missing_facts": ["补交易所公告/链上地址/安全通报或原帖链接"]
}
```

### bad example

```json
{
  "main_post": "某交易所已经暂停提币，大家快撤。",
  "first_comment": "",
  "visual_prompt": "",
  "editor_risk_note": "",
  "need_fact_check": false,
  "weak_points": []
}
```

为什么错：把二手信息写成确定事实，且制造恐慌。

### good example

```json
{
  "main_post": "这条消息别急着当成「已坐实」。\n\n目前更像是一个风险信号：市场在传某交易所出现提币相关异常，但缺关键锚点（官方公告/链上地址/安全通报）。\n\n如果你要跟这条线，先盯「证据」而不是盯情绪。",
  "first_comment": "更值得盯的不是「有没有暂停提币」这句传闻，而是下一步证据会落在哪里。\n\n只要官方公告/链上流出/安全通报三者里出现一个硬锚点，这条线就从情绪变成事件。",
  "visual_prompt": "一张「证据清单」信息图：公告/链上地址/安全通报三栏，当前状态标记为待补齐。",
  "editor_risk_note": "边界：不要写成确定暂停提币。需要补：交易所官方公告、链上地址与流出证据、安全团队通报。高风险题材；缺锚点时只能写成监测信号；禁止自动发布。",
  "need_fact_check": true,
  "weak_points": ["来源偏二手", "缺官方公告/链上证据/安全通报"]
}
```

---

## 示例 2｜good：有钩子，但不标题党

```json
{
  "event_cluster_id": "e_ai_entry",
  "cluster_title": "某 AI 产品接入支付入口",
  "cluster_queue": "queue_review",
  "risk_level": "low",
  "best_source_url": "https://example.com/official",
  "missing_facts": []
}
```

### good example

```json
{
  "main_post": "AI 这条线真正的进展，可能不在模型参数，而在「入口」。\n\n当它开始摸到支付/账户这种位置，故事就从演示变成了用户动作。\n\n这条消息值得看的点：它会不会让某个产品从「能用」变成「每天都用」。",
  "first_comment": "更大的问题是：入口一旦被占住，竞争就从「功能」变成「习惯」。\n\n接下来盯两件事：它有没有真实交易闭环、用户是不是每天都离不开这个入口。",
  "visual_prompt": "用一张「入口路径图」：用户从哪里触发→到支付/账户→最终动作。",
  "editor_risk_note": "避免夸大落地与增长；不要写投资建议。",
  "need_fact_check": false,
  "weak_points": []
}
```

---

## 示例 3｜bad vs good：首评写成审核备注（太扫兴）

### bad example（首评像审稿清单）

```json
{
  "main_post": "（略）",
  "first_comment": "几个可以核验的细节：\n① 原始报道来自...\n② Claude 并非破解...\n③ 社区质疑...",
  "visual_prompt": "",
  "editor_risk_note": "",
  "need_fact_check": false,
  "weak_points": []
}
```

### good example（首评补观察与场景）

```json
{
  "main_post": "（略）",
  "first_comment": "这事最有意思的地方，不是 Claude 多神。\n\n而是很多所谓「丢失的钱包」，可能并不是资产真的消失了。\n\n它们只是散落在旧电脑、旧邮箱、旧硬盘、旧备份里，没人知道从哪里开始找。\n\nAI 在这里更像一个不会烦的数字侦探。\n\n它不创造私钥。\n\n它只是帮你把十年前的线索，一条条翻出来。",
  "visual_prompt": "",
  "editor_risk_note": "如果涉及安全/私钥/助记词：明确禁止提供任何可操作的找回步骤与链接，避免引导风险。",
  "need_fact_check": false,
  "weak_points": []
}
```

---

## 示例 4｜good：主帖不超 280，首评不清单化（Claude 找回 BTC）

```json
{
  "main_post": "一个人找了十年的比特币，最后靠 Claude 找回来了。\n\n5 枚 BTC，约 32 万美元。\n\n他没有让 AI 破解钱包，而是让 Claude 系统性地翻旧电脑、旧硬盘、iCloud 邮件和备份文件，最终找到了当年的助记词。\n\n这事最有意思的地方是：很多「丢失」的比特币，可能只是藏得太深。",
  "first_comment": "AI 在这里不像黑客，更像一个不会烦的数字侦探。\n\n它不创造私钥。\n\n它只是帮你把十年前散落在旧设备里的线索，一条条翻出来。",
  "visual_prompt": "一张「数字侦探」风格插画：旧电脑、硬盘、邮箱、云盘四个线索盒子被逐个打开，线索汇聚到一张纸条「助记词」。",
  "editor_risk_note": "边界：不要提供任何可操作的找回教程/链接/话术，不要引导输入助记词；只描述“翻找线索”的方法论层面即可。",
  "need_fact_check": false,
  "weak_points": []
}
```
