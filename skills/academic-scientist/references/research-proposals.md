# 第七阶段：单路线研究方案与可编辑图

用户已确认：先通过补充询问确定一条研究路线，再生成一个详细框架；流程图默认中文，保留模型名和必要英文术语。不要把第六阶段的多个阅读角度自动变成多套研究方案，也不要直接替初学者定题。

## 澄清与方案生成

1. 使用当前已复核的第六阶段 run，start 或 show 恢复。沿用三轮探索卡和阅读建议，不重复三轮问答；补充询问只覆盖会改变方案的问题。
2. 先问主要研究路线，再根据回答确认实验边界。每次 ask 后等待真实回答再 answer，记录原话及来源；不得模拟、默选或以超时为确认。补充轮数按需要，不固定三轮。
3. 答案足够明确时 select 记录单一路线和逐字引用。select 是对已收到决定的记录，不是要求额外确认一次。若答案仍模糊，继续问；路径或科学意图不能靠字符串匹配替用户判断。
4. 列出研究问题、待检验假设、方法、数据条件、基线、指标、消融、最小实验、失败判据及局限。每个段落区分文献已有做法、拟议设计、未知条件。
5. 关键事实只来自给定文献的已复核断言，精确绑定论文、字段和证据。借鉴不等于可直接迁移，未提供材料不能说全文没有报告。“给定材料未见”不等于首次提出。模型和预算未知时保留前置条件，不制造数据集或预期结果。
6. 启动真实实验前须明确数据、指标和预算；本阶段生成的是未执行方案。提出 MAE/RMSE 等指标时标为方案建议；数字阈值、样本量、预期提升不凭空填写。用户只授权设计时不下载模型、训练或启动外部任务。
7. submit 后由当前 Agent 回看原话、引用证据和实验逻辑，再 review；结构检查不能证明科学正确性。没有独立人工审查时如实标记 Agent 复核。

## 实验设计需要核查的关系

- 研究问题与数据/目标是否对应；哪些条件尚待确认。
- 对照是否控制数据划分、工具、模型、预算与搜索空间；改变多个变量时不要做单因素因果解释。
- 区分训练、验证和最终测试；测试集不能通过 Agent 的反馈回路重新参与调参。
- 明确输出核查、异常与失败计入方式，不删除失败试验以制造收益。
- 写最小可证伪实验及不支持假设的情形，不把待检验假设写成结论。
- 实际模型适用性与研究新颖性需要进一步证据；不是增加严格审批流程，而是诚实保留未验证状态。

## 字段字典 v0.7.0

Schema：[research-proposal](../schemas/research-proposal.schema.json)、[proposal-run](../schemas/proposal-run.schema.json)、[figure-review](../schemas/figure-review.schema.json)。不改论文事实 v0.1.0 或第六阶段学习理由契约。

| 对象 | 字段与含义 |
|---|---|
| run | source_kind=agent_proposal、purpose、revision、saved_at、reason；purpose 从上游继承 |
| upstream | 第六阶段完整快照及 upstream_digest、recommendation_run 路径；复用前检查是否仍当前且通过审阅 |
| dialogue | 问题 id、question、reason、时间与 answer；answer 含真实 text、user_ref、时间，无回复时为 null |
| route | 单个 id、label、answer_ref、quote、reason；不得用数组选多路线，quote 必须来自已收到的回答 |
| plan | title、route_id、source_kind=agent_proposal；execution_status=not_run、novelty_status=not_assessed |
| sections | problem、hypothesis、approach、data_plan、baselines、evaluation、ablations、minimal_experiment、failure_criteria、limitations；每组至少一个 statement |
| statement | 唯一 id、kind、text、verification、goal_refs、fact_refs；verification 写怎样核查或验证 |
| kind | borrowed：文献已有做法，需 supported 依据；proposal：本方案拟采用/待验证；unknown：尚缺条件 |
| goal_refs | source=card 时 ref 为探索卡1起的序号字符串；source=answer 时 ref 为本阶段实际回答的问题 id |
| fact_refs | paper_id、assertion_id、evidence_ids；证据必须属于该论文断言；无事实主张时可空 |
| assumptions | id、text、risk、verify；区分假设、风险及未来验证方式 |
| graph.nodes | id、label、kind、phase、statement_refs；phase 为 input/training/inference/evaluation/output/shared |
| graph.edges | id、source、target、relation、label、statement_refs；relation 为 data/control/feedback/update |
| review | 候选 digest、审阅者/时间/说明、accepted/rejected、evidence/feasibility/graph_alignment 三项检查；全部 true 才接受 |
| figure-manifest | 方案内容摘要、XML/SVG 摘要、节点/边到段落映射；记录实际渲染方式与原生核查状态 |
| visual-review | 至少三次实际截图及各次对应源 XML、检查说明、最终 PDF/纸面截图的哈希、审阅者；不是自动正确性证明 |

graph 的每个节点和边必须对应方案段落；未知不能涂为已知，拟议操作不能涂为文献既有组件。节点连通、有明确输入输出，端点和引用不能缺失。脚本不能理解所有标签含义，graph_alignment 仍要求 Agent 实际核对方向和语义。

## 图形交付（当前默认三视图）

2026-10-07 起，用户已确认一次交付整体框架、关键模块详图、实验流程图。新方案按 [三视图契约与操作](figure-sets.md) 填写可选扩展 figure_set，默认使用 export-set、review-figure-set、figure-set-status。该扩展保持 v0.7.0 旧方案可读取；历史的单图操作继续用于旧文件。

先定语义再排版。使用 draw.io 原生可编辑矩形、文字和连接线，不把整张图做成不可编辑位图。默认横向5–8步骤：输入→处理→关键方法→评估/输出。蓝色表示文献组件，珊瑚色表示拟议设计，米黄色表示条件未知；图例必须说明。实线数据流，虚线控制/反馈/更新。

旧版 proposal_figures 概览生成器支持2–8节点；此限制不适用于新的 figure_sets 三视图生成器。新生成器接受显式位置、端口、折点和分组，详图与实验图可超过8节点。它不提供任意网络的自动布局；由 Agent 依据语义编排并检查，不为排版省略必要关系。

生成 `.drawio`、从同一 XML 图元解析的 `.svg`、节点/段落映射和方案 MD/JSON。本地 SVG 渲染器只支持本脚本的图元，不是 diagrams.net 原生引擎；任意手工新增原生形状应使用 draw.io 自身导出，不强行用本地预览器解释。

渲染能力可用时生成 PNG/PDF 并检查：页面裁切、字级、箭头、颜色、语义对应和论文宽度下的可读性。若安装了 academic-figures-drawer，可使用其静态检查和审查流程；本 skill 不依赖其绝对路径或自动安装。

用户重要图形执行至少三次实际截图检查，九区覆盖，不虚构缺陷或审查记录。源文件、预览和审阅记录绑定内容哈希；预览或图被修改即需重新检查。尚无原生 draw.io 渲染验证时 native_drawio_render_verified=false，不能写成原生兼容或 camera-ready 已独立验收。

## CLI

```powershell
python -B -X utf8 "<SKILL>/scripts/research_proposals.py" --root "<ROOT>" --run "work/my-proposal" start --input "work/proposal-start.json"
```

start 请求：`{"recommendation_run":"work/my-reading-run","reason":"进入方案澄清"}`。路径全部相对于指定工作根目录；保存在根目录内。后续动作除 show/status/export/figure-status/export-set/figure-set-status 外都携带最新 expected_revision 和非空 reason。

| action | 主要请求内容 | 行为 |
|---|---|---|
| show / status | `{}`；show 可选 revision | 恢复当前/历史，检查待回答、路线、审阅和输入版本 |
| ask | question | 保存一个补充问题；已有待答时拒绝新问题 |
| answer | question_id、text、user_ref | 保存当前问题的真实回复 |
| select | route 对象 | 基于实际回答确定单一路线；有待答则拒绝 |
| submit | plan 对象 | 保存方案候选；变更清除旧审阅，同内容幂等 |
| review | decision、reviewer、note、evidence、feasibility、graph_alignment | 保存语义复核；不等于独立人工认可 |
| refresh | reason | 更新上游；清除方案/审阅，目标变更还重置当前补充问答和路线，旧版本保留 |
| export | `{}` | 有 figure_set 自动导出三视图；旧方案沿用单图。visual_review_required=true 表示随后还要审图 |
| export-set | `{}` | 要求完整 figure_set；一次导出三图与三页总文件，缺图报错，不降级为单图 |
| review-figure-set / figure-set-status | 见三视图操作 | 整组记录与失效检查；不可用旧单图检查代替 |
| review-figure | export_folder、cycles、pdf、paper_scale_image、reviewer、notes、四项检查 | 保存图形审阅记录；cycle 含 screenshot/source_drawio/notes，均为根目录内相对路径 |
| figure-status | export_folder | 检查图与方案、预览哈希及审阅是否仍对应当前输入 |

review-figure 的四项布尔检查为 text_readable、arrows_clear、semantics_match、paper_scale_checked。delivery_ready 只表示已绑定当前方案和已记录的视觉证据，不代表科学方案已经验证，也不代表 draw.io 原生兼容性已核查。

## 版本、修改与恢复

上游推荐变化先 refresh。目标相同的论文/分析更新保留真实补充回答与路线，但重做方案；目标改变需重新澄清，历史回答仍保存在旧版本。新增问题或改路线会使旧方案失效。

每次导出目录绑定方案版本和渲染器指纹，样式调整使用新目录，旧文件保留。用户改过 MD/draw.io/SVG 时拒绝覆盖；修改科学语义须先更新方案及对应图，再复核。自由排版修改只留原图，不自动逆向回填论文事实或方案文字。

中断恢复先 show/status，读实际待答记录；不要重放开发脚本冒充新的用户对话或重新阅读。依赖缺失时先确认安装，不能修改全局环境。第八阶段整体评测不会因本阶段结束而自动启动。
