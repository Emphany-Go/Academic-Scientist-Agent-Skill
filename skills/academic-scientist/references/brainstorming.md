# 三轮研究探索：操作与数据契约

第二阶段已实现持久状态与来源检查。问题及探索卡由当前 Agent 根据真实对话设计；脚本不调用额外模型，也不凭关键词自动决定课题。

## 与用户交互

1. 保存用户的原始想法（不重写成你猜测的目标），使用可回查的消息引用。
2. 第一轮：解释少量容易理解的场景，追问兴趣/动机；已有明确问题则进一步澄清关键假设。每轮 1–2 个问题。
3. 等待真实回答；使用对话的用户输入工具或普通提问。暂停/中断只恢复待回答状态，不推测或自动提交回复。
4. 第二轮：依据上一轮回答提出 2–3 条候选路径并说明区别，再问最影响后续阅读的问题；不要强制用户立刻选算法。
5. 第三轮：确定阅读目的或关键条件，接受“不知道”和保留多个方向，不把未知当成不匹配。
6. 三轮实际回答完成后生成探索卡，无第四轮强制确认。展示明确偏好、Agent 候选建议及未知项，用户可以随时修订。

每轮先形成解释和问题，写入 ask 状态，再向用户展示。恢复会话时重现同一待答问题；若上次已收到但尚未落盘的用户回答仍在对话中，应核对消息引用后补记一次，不能再次让用户回答。不要把开发本 skill 的意见当作正在运行的某次研究探索。

## 状态

`initial → round1_wait → round1_answered → round2_wait → round2_answered → round3_wait → ready`

answered 是实现需要的中间状态：上一轮回答已存储，下一轮问题尚未生成。每个写入携带 expected_revision，过时或缺失的版本被拒绝；原始回答和历史快照不修改。

session `purpose=live` 用于实际用户对话，`synthetic_test` 只用于明确标注的虚构测试。user_ref 由 Agent 对真实消息做引用；脚本能检测重复和缺失，不能独立证明调用者未伪造消息，真实性由实际对话和 Agent 遵循规范保证。

## 探索卡条目

| 属性 | 含义 |
|---|---|
| category | interest / candidate_direction / reading_goal / constraint / research_stage / unknown / suggestion |
| text | 忠实概括或明确标注的建议 |
| origin | user_explicit / agent_proposal / unresolved |
| source_quotes | 原始消息的精确短片段；source_ref 为 initial、answer1–3 或 amendment1… |

用户明确条目必须带用户原话；unknown 必须 unresolved，suggestion 必须 agent_proposal。精确匹配引用只证明引用存在，不证明语义概括正确，输出前要检查是否曲解，特别是“没有数据”和“不想使用数据”的区别。

如果用户用序号选项回答，卡片须结合保存的问题上下文解释，原话仍保留该序号。不得把 Agent 举例的算力、数据量或题目直接记录为用户条件。原始想法、完整三轮问答、修订与条目都保存在 JSON。

## 命令接口

使用 [项目规范](project-workspace.md) 返回的内部工作根目录ROOT。输入为 UTF-8 JSON 文件，不在命令行拼接用户原话。

```powershell
python -B -X utf8 "<SKILL>/scripts/research_session.py" --root "<ROOT>" --session study-01 init --input "<ROOT>/init.json"
```

操作与输入（除 init/show/export 外都包含最新 expected_revision）：

| action | 输入 |
|---|---|
| init | text 原始想法、user_ref 真实消息引用；purpose 默认 live |
| show | 不需输入；读取当前状态，不推进轮次 |
| ask | context 引导说明、questions 1–2 个问题、based_on 为 initial 或最近一轮 answerN |
| answer | text 实际回答、user_ref 唯一消息引用 |
| card | entries 探索卡条目；仅 ready 后执行；修正已有当前卡时必须提供 revision_reason，保留新旧版本 |
| amend | ready 后的真实用户更正 text、user_ref；旧卡保留，新卡待生成 |
| export | 重新生成缺失的卡片 JSON/Markdown 导出，不改变状态或覆盖现存导出 |

ask 输入示例（结构示意，不是用户的真实问答）：

```json
{
  "expected_revision": 1,
  "context": "可以先从使用场景和希望改善的问题入手，暂时不必确定模型。",
  "questions": ["你最希望改善哪种具体困难？也可以先描述一个实际场景。"],
  "based_on": "initial"
}
```

## 修订与恢复

- 研究讨论未结束时，用户更正内容并入当前轮实际回答，后续提问使用新的表达；不伪造额外回答。
- ready 后用 amend 保存真实更正，card_stale=true；生成新卡为新版本，旧卡及原始问答保留。
- 卡片 Markdown/JSON 是当时版本的导出，不自动导入人工编辑。用户改变目标时通过 amend 记录真实更正。Agent 发现自己的概括不忠于原始回答时，可给 card 提供 revision_reason 纠正并保留旧版，向用户说明；不能伪造用户更正或改变用户意图。确实无法判断意图时先向用户确认。
- 新论文可复用 ready 探索卡，目标不变时不要重跑三轮。带新版本探索卡的分析将在后续阶段生成。
- 写入采用系统锁和原子快照。进程异常退出后系统会释放锁，恢复时读取最后完整快照，不删除历史。锁文件存在本身不代表被占用。

结构定义见 [session schema](../schemas/research-session.schema.json) 和 [card schema](../schemas/research-card.schema.json)。
