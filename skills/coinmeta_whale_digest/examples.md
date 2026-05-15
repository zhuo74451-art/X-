# Examples（bad vs good）

下面每组示例都强调：输入是 actor_daily_pack（聚合包），输出要“总结今天整体在干嘛”，不是流水账。

---

## 示例 1｜麻吉多次调仓（聚合写法，不写流水账）

### 输入（节选）

```json
{
  "column_name": "今天巨鲸在干嘛",
  "time_window": "2026-05-14 00:00-24:00 UTC",
  "generated_at": "2026-05-14T08:00:00Z",
  "actors": [
    {
      "actor_label": "麻吉交易员A",
      "actor_type": "celebrity_trader",
      "why_selected": "当日多次调仓且净方向明显，关注度高",
      "actions_count": 7,
      "main_assets": ["HYPE", "ETH"],
      "net_direction": "rotate",
      "net_amount_usd": 1800000,
      "realized_pnl_usd": -320000,
      "unrealized_pnl_change_usd": -210000,
      "risk_change": "higher",
      "summary_line": "短线多次换手，净敞口上升，风控边界变窄",
      "notable_actions": [
        "多次在同一价区间加减仓，净敞口抬升",
        "出现补保证金动作"
      ],
      "source_links": ["https://example.com/dashboard/xxx"],
      "confidence": "medium",
      "do_not_claim": ["不要写成「确定要爆仓」"]
    }
  ]
}
```

### bad example（错误）

```json
{
  "main_post": "麻吉交易员A 00:10 买入HYPE，00:35 卖出HYPE，01:20 买入ETH，02:05 卖出ETH……（省略）",
  "first_comment": "更多交易如下：……",
  "visual_prompt": "画一张图",
  "editor_risk_note": "无",
  "need_fact_check": false,
  "weak_points": []
}
```

为什么错：
- 把栏目写成流水账，读者看不出“整体在干嘛”
- 没有风险变化总结，也没有可核验点提示

### good example（更好）

```json
{
  "main_post": "今天「麻吉交易员A」更像在做一件事：不断换手，把净敞口抬上去。\n\n动作很多，但重点很简单：仓位更大了，容错更小了。\n\n这种盘面里，最值得盯的不是他下一笔买卖，而是他会不会继续补保证金、或者开始被动减仓。",
  "first_comment": "边界：不要把「可能被动减仓」写成确定爆仓。\n\n可核验点：看板里能看到当日净敞口变化与补保证金动作（见 source_links）。\n\n观察指标：保证金动作是否持续、净敞口是否继续上升。",
  "visual_prompt": "用一张「净敞口曲线 + 当日补保证金标记」的小图，右侧列3个观察点：敞口、保证金、回撤。",
  "editor_risk_note": "避免暗示跟单；不要写成交易建议；对「风险增加」用事实描述（敞口/回撤/保证金）。",
  "need_fact_check": false,
  "weak_points": []
}
```

---

## 示例 2｜HYPE 大多头补保证金（写清风险变化）

### 输入（节选）

```json
{
  "column_name": "今天巨鲸在干嘛",
  "time_window": "2026-05-14 00:00-24:00 UTC",
  "generated_at": "2026-05-14T08:00:00Z",
  "actors": [
    {
      "actor_label": "HYPE 大多头",
      "actor_type": "whale",
      "why_selected": "仓位大且风险边界变化明显",
      "actions_count": 3,
      "main_assets": ["HYPE"],
      "net_direction": "add_leverage",
      "net_amount_usd": 0,
      "realized_pnl_usd": 0,
      "unrealized_pnl_change_usd": -13000000,
      "risk_change": "higher",
      "summary_line": "回撤扩大后补保证金，风险从「舒服」变成「紧」",
      "notable_actions": [
        "回撤扩大",
        "出现补保证金动作",
        "存在清算风险提示"
      ],
      "source_links": ["https://example.com/tg/post/123"],
      "confidence": "medium",
      "do_not_claim": ["不要写成「已经接近清算价」除非输入明确给出"]
    }
  ]
}
```

### bad example（错误）

```json
{
  "main_post": "HYPE 大多头补保证金，说明马上要爆仓了。",
  "first_comment": "大家注意风险。",
  "visual_prompt": "",
  "editor_risk_note": "",
  "need_fact_check": false,
  "weak_points": []
}
```

为什么错：
- 把补保证金直接推导成确定爆仓（越界）
- 缺乏“风险变化”与“观察指标”的人话解释

### good example（更好）

```json
{
  "main_post": "今天 HYPE 这条线的紧张感，来自「仓位」而不是「叙事」。\n\n某大多头在回撤扩大后选择补保证金——这不是方向判断，这是在把风险线往后挪。\n\n一句话：仓位还在，但安全垫变薄了。",
  "first_comment": "边界：不要写成确定爆仓；除非输入明确给出清算价。\n\n观察指标：后续是否继续补保证金、是否出现被动减仓、资金费率是否继续放大。\n\n如果 source_links 只有二手转述，建议编辑先补更硬的看板/截图再发。",
  "visual_prompt": "配一张「回撤变化 + 保证金动作」的简图：左侧回撤柱状，右侧标注「补保证金」时间点。",
  "editor_risk_note": "避免「跟单」暗示；用「风险线/安全垫」这类人话描述，不写价格预测。",
  "need_fact_check": true,
  "weak_points": ["缺清算价/缺仓位截图或看板链接"]
}
```

---

## 示例 3｜休眠 ETH 巨鲸转账（写出市场紧张感）

### 输入（节选）

```json
{
  "column_name": "今天巨鲸在干嘛",
  "time_window": "2026-05-14 00:00-24:00 UTC",
  "generated_at": "2026-05-14T08:00:00Z",
  "actors": [
    {
      "actor_label": "休眠ETH巨鲸",
      "actor_type": "whale",
      "why_selected": "休眠地址重新活跃，容易引发情绪波动",
      "actions_count": 1,
      "main_assets": ["ETH"],
      "net_direction": "unclear",
      "net_amount_usd": 0,
      "realized_pnl_usd": 0,
      "unrealized_pnl_change_usd": 0,
      "risk_change": "unclear",
      "summary_line": "休眠地址动了，市场会先紧张一下",
      "notable_actions": ["休眠地址出现转出动作（去向未确认）"],
      "source_links": ["https://example.com/scan/0xabc"],
      "confidence": "weak",
      "do_not_claim": ["不要写成「要砸盘」"]
    }
  ]
}
```

### bad example（错误）

```json
{
  "main_post": "休眠ETH巨鲸要砸盘了，大家快跑。",
  "first_comment": "",
  "visual_prompt": "",
  "editor_risk_note": "",
  "need_fact_check": false,
  "weak_points": []
}
```

为什么错：
- 直接把“转账”写成“砸盘”（越界 + 容易误导）

### good example（更好）

```json
{
  "main_post": "今天 ETH 盘面里最容易引发情绪的，不是涨跌，是「休眠地址动了」。\n\n它不一定代表卖压，但会先把市场的紧张感拉起来：大家会盯去向、盯交易所流入、盯后续是否连续动作。\n\n这种信号更适合放进「巨鲸日报」持续追踪，而不是单条硬推结论。",
  "first_comment": "边界：不要把转账写成卖出；除非输入明确出现「转入交易所」或实际卖出证据。\n\n可核验点：链上链接/看板（source_links）。\n\n观察指标：去向是否为交易所、是否连续多笔、是否伴随交易所净流入变化。",
  "visual_prompt": "用一张「地址活跃时间线 + 去向标记」的小图，突出「休眠→活跃」的时间点与去向。",
  "editor_risk_note": "避免制造恐慌；避免价格预测；保持「不一定=但值得盯」的语气。",
  "need_fact_check": true,
  "weak_points": ["去向未确认", "缺交易所流入/流出佐证"]
}
```
