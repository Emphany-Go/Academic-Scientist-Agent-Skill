# 第六阶段：相关性分析与阅读推荐

已实现来源绑定、五维分析、四方面学习理由、证据引用、复核、历史版本、失效检查和 Markdown/JSON 输出。用户于 2026-10-04 明确：“不进行量化评分，只从方法、背景、实验设计、模型选择等层面给出值得借鉴或学习的理由”。因此不计算分数、不设优先级分层、不按推荐强弱排序。第七阶段研究方案和绘图不在本阶段执行。

## 输入和真实性边界

- 输入为第二阶段 ready 探索卡、第五阶段已复核集合及其原文副本。必须是当前探索卡；没有三轮真实回答不得用于 live 分析。
- 分别保存研究目标、论文事实、Agent 分析。`user_explicit` 目标必须有对应的真实原话；未知条件不能变成已知约束，Agent 提议不能伪装用户已确定路线。
- 按问题或阅读切入点建立方向，一篇论文可以服务多个方向。初学者可以保持多个候选方向，不强迫先定题。切入点由 Agent 组织时标记 `agent_proposal`。
- 只引用所绑定论文中已复核 assertion 和属于它的 evidence。需要新增事实时回第三阶段复核，再同步集合；禁止通过联网或模型记忆补进论文事实。
- 只有“已获 Agent 复核”才称 Agent checked；复核布尔值和结构校验不能证明推理必然正确，更不能冒充独立人工验收。
- partial 可用于有限分析，明确缺失范围。未提供补充材料不等于论文未报告。未知与不匹配分开；期刊评级、个人笔记和待核查修改不进入事实快照或相关性权重。

## 分析字段字典（v0.6.0）

契约文件：[relevance-entry](../schemas/relevance-entry.schema.json)、[recommendation-run](../schemas/recommendation-run.schema.json)。论文的 34 个事实字段及 v0.1.0 契约不变。

| 对象/字段 | 含义与要求 |
|---|---|
| binding | `session_root`、`session_id`、`collection`；根目录内的相对路径与真实会话 ID |
| snapshot | 探索卡、每篇 record 和 source_files、会话/集合版本、卡与论文内容哈希；不含笔记、平台卡或 pending 修改 |
| directions | `id`、`label`、`goal_refs`、`origin`；候选方向或阅读切入点，不代表批准的研究方案 |
| goal_refs | 从 1 起的探索卡 entries 序号；只对快照版本有效，目标改变后重建 |
| fact_refs | assertion_id 与 evidence_ids；原文定位必须属于该断言，supported 不允许空定位 |
| claim | text + goal_refs + fact_refs；说明目标与文献怎样对应；单纯目标未知可无事实引用 |
| entry | paper_id、direction_id、source_kind 固定 agent_analysis；一篇论文和一个方向的组合 |
| assessments | 恰好五个维度，各含 relation、explanation、conditions、unknowns |
| summary | 该方向下阅读价值概述，引用该方向目标和已复核断言；不能只重复标题 |
| use_cases | background / close_reading / baseline / method_borrowing / counterexample，及各自有证据的理由；这是用途而非最终优先级 |
| reading_targets | evidence_id + purpose；必须是分析引用过的真实页、章节、图或表，不能猜章节 |
| learning_points | 恰好四项 aspect：method / background / experimental_design / model_selection；每项含 status、explanation（claim）、questions_to_check |
| learning_points.status | actionable：有 supported 事实、明确用户目标和阅读位置支持学习价值；insufficient_evidence：证据不足，列出需补充信息，不强行给理由 |
| limitations | 至少一项限制或待明确条件，区分作者明确局限与 Agent 迁移判断 |
| open_questions | 影响后续阅读/推荐的未知条件，不是新一轮强制确认门槛 |
| reviews | 对候选内容哈希的 accepted/rejected、审阅者、时间、说明和三个检查结果 |
| revision / reason | 每次修改追加版本及原因；expected_revision 防止并行覆盖；同内容 submit 幂等 |
| purpose | live 或 synthetic_test，从探索卡继承；合成测试输出显式标记 |

五个维度：`problem_fit` 研究问题、`data_fit` 数据适配、`method_transfer` 方法迁移、`resource_fit` 资源可行性、`reading_goal_fit` 阅读目的。学习阶段可结合真实用户目标解释，不凭身份猜测。

四个学习方面回答不同问题：方法——哪些步骤/模块可借鉴；背景——怎样理解问题与方法的关系；实验设计——基线、变量控制、划分、指标或消融值得学什么；模型选择——各组件为何用于该任务、来源和改动是什么。不得猜测作者未解释的选择理由；“可学到的比较方式”是 Agent 分析，不等于作者证明的因果解释。材料实验论文无计算模型时，模型选择可标证据不足并说明不适用原因，不强行补模型。历史底稿可缺 learning_points 以便恢复，但正式导出必须补齐并重新复核。

关系枚举：direct 直接相关、partial 部分相关、transferable 有条件可迁移、mismatch 已知条件不匹配、unknown 尚无法判断。非 unknown 必须引用 supported 事实和真实用户目标；transferable 必须列迁移条件；unknown 必须说明缺什么。未知算力不等于成本过高，任务不直接匹配不等于方法没有借鉴价值。

## Agent 操作

1. 恢复已有 run 时先 show/status。新 run 先读目标原话与事实证据，确认来源完整，再 start。
2. 按“每个方向 × 每篇论文”逐项分析。只写证据能够支持的结论，未知单列；不可将不同数据、划分、指标、单位的数值直接比较或声称性能更好。
3. 解释每篇适合学什么、如何迁移、哪里不能套用；阅读位置写页码及图表/章节的实际定位，并说明要核对的内容。缺乏可用证据时保留 unknown，use_cases/reading_targets 可以为空，不编造推荐。
4. submit 后回看目标原话、引用值及原文证据上下文，核查不确定性。需要进一步原文检查时实际查看 PDF，不以脚本验证替代语义检查。
5. review 的三个检查项是 evidence_fidelity、goal_alignment、uncertainty_handling；只有全部 true 才能 accepted，说明实际做了什么。候选修改自动清除旧复核。
6. 每组都审阅且来源最新后 export，生成 reading-guide.md 与 reading-guide.json：包含目标、五维矩阵、四方面学习理由、阅读定位、条件和局限。无可用证据的方面显示未知，不强行推荐。论文按内部 ID 稳定展示，顺序没有评价含义。export-analysis 可另外输出分析底稿；底稿完成不等于四方面推荐已完成。

## CLI 与请求

所有请求文件保存在工作目录内。示例路径需换为实际路径；新建 run 用未占用目录。命令形态：

```powershell
python -B -X utf8 "<SKILL>/scripts/recommendations.py" --root "<ROOT>" --run "work/my-analysis" start --input "work/start-analysis.json"
```

start 请求示例（路径和 ID 须对应已有输入）：

```json
{
  "binding": {"session_root": "work/study", "session_id": "study", "collection": "work/collection"},
  "directions": [{"id": "method-reading", "label": "理解方法及实验", "goal_refs": [1], "origin": "agent_proposal"}],
  "reason": "根据已完成探索卡建立阅读分析"
}
```

| action | 请求字段 | 结果 |
|---|---|---|
| show | `{}`；可选历史 revision | 当前/历史 run 和来源状态 |
| status | `{}` | freshness、accepted、pending、analysis_ready、learning_pending、recommendation_ready |
| submit | expected_revision、reason、entry | 新版本；entry 必须符合上述 Schema |
| review | expected_revision、reason、direction_id、paper_id、decision、reviewer、review_note、三个检查布尔值 | 对该候选哈希的审阅 |
| refresh | expected_revision、reason；可选 directions | 绑定最新输入，保留未受影响分析；不自动生成新判断 |
| export-analysis | `{}` | analysis-exports/rNNNNNN/analysis.md 和完整 JSON 快照 |
| export | `{}` | exports/rNNNNNN-reading-v2/reading-guide.md 和 JSON；presentation=learning_reasons、scoring=false、priority_tiers=false；版式版本变化使用新目录保留旧导出 |

所有动作都用 --input 提供 JSON，避免命令行引号改变文本。内容需修改时走 submit/refresh，不手改 revisions。

## 更新与恢复

- 研究卡/方向变化：清除当前候选与复核，保留历史版本；所有论文重新关联新目标，原始事实不重新抽取。
- 论文事实或来源变化：只保留未变论文的分析和复核；新增论文要对每个方向分析，删除论文不再列入当前清单。
- 笔记、官方评价或集合其他元数据变化：不改变科学分析的来源内容，不伪造事实更新。
- 引用原文缺失、被修改、卡过期或输入结构异常：status 标记失效，不能当作当前推荐。修复上游后 refresh 再复核。
- 全部导出带固定版本；文件不会自动刷新，复用先 status。导出的 Markdown 有人工修改时拒绝覆盖；保留原件，新增版本后导出新路径，不能静默迁移自由文字。

## 当前验收边界

已用真实两篇聚合物论文与三轮探索卡创建四份分析、16 项学习理由，复用先前已复核事实并核对所引摘录，不宣称本轮重新全文抽取。两篇缺补充材料仍为 partial。自动测试覆盖引用、未知条件、审阅门槛、四方面内容、禁止评分字段、来源变更、历史和导出保护；不代表语义准确率。用户对本阶段实际建议的独立验收尚未完成。
