# 字段字典 v0.1.0

## 填写规则

每个字段包含 value、状态、证据 ID、复核状态及必要说明。非缺失值只能由提供文献支持；原文没说则不补。多个模型、结果或结论分别记录，不能塞进一个不可拆分的长单元格。

标记“必查”的组必须检查，但不等于必须有值。扫描失败、缺附录、只读摘要时无法证明“未报告”。状态见 evidence-rules.md。

## 字段清单

机器可读版本为 `../schemas/field-catalog.json`。层级 paper=论文、model=模型/模块、experiment=单个实验条件。除明确数值或枚举外，保存忠实的中文概括并保留原术语。

| ID | 中文名称 | 层级 | 取值与依据 |
|---|---|---|---|
| title | 标题 | paper | 正文首页标题，不能凭文件名填写 |
| authors | 作者 | paper | 作者字符串列表，保留顺序；单位不当作者 |
| publication_year | 正式发表年份 | paper | 整数；正式卷期、会议题录或明确出版信息；不使用收稿日、PDF 创建日期或预印本年份 |
| venue | 期刊或会议 | paper | 文献明确给出的名称，保留实际主会/Workshop 名称 |
| research_objective | 研究目的 | paper | 作者陈述的目标 |
| prior_limitations | 已有方法不足 | paper | 作者对已有工作的描述，不是 Agent 自行批评 |
| hypothesis | 研究假设 | paper | 只提取明确假设，不能从目的补造 |
| application_scope | 应用范围 | paper | 作者界定的任务、材料或应用场景 |
| method_overview | 总体思路 | paper | 有证据的流程概括，不添加未描述步骤 |
| model_inventory | 模型清单 | paper | 内部 model ID 列表；无模型须核查后标不适用；未检查不能用空列表表示无模型 |
| model_name | 模型名称 | model | 文献中的名称与明确版本；未给版本不猜 |
| model_function | 模块功能 | model | 作者说明的功能 |
| model_io | 输入输出 | model | 文献支持的输入输出与维度；不自动推导维度 |
| training | 训练方式 | model | 有报告才填写；材料本构或解析模型通常不适用，需说明 |
| model_origin | 模型来源类别 | model | 七类标签，多标签见下文 |
| source_attribution | 原模型来源 | model | 本文给出的作者/名称/引用编号及改动；不能声称已读未提供的被引论文 |
| dataset | 数据集或实验对象 | experiment | 计算机论文的基准集；材料论文的样品/材料体系。材料种类不假称数据集 |
| sample_size | 样本量 | experiment | 样本/重复/试件数量的原文描述，注明单位与统计对象 |
| split | 划分方式 | experiment | 训练/验证/测试划分；没有此概念则有依据地不适用 |
| preprocessing | 预处理 | experiment | 原文报告的数据处理或样品制备处理；以原术语区分 |
| baselines | 对照方法 | experiment | 对照模型/配方/条件的明确名称与作用 |
| ablation | 消融或因素对照 | experiment | 原文中的控制变量比较；不要把所有材料实验强称消融 |
| hyperparameters | 超参数或实验设定 | experiment | 计算机训练参数；材料实验温度、压力、配比等归入实验设定并注明含义 |
| model_scale | 模型规模 | model | 原文报告的参数量等，不能自行计算补全 |
| compute_resources | 计算资源 | experiment | 计算硬件、训练时间等；物理仪器信息保存在实验条件，不视为计算资源 |
| metric | 指标名称与定义 | experiment | 原文指标，保留统计口径和方向（仅当报告） |
| result | 结果值 | experiment | 数值/字符串，不跨条件合并；保留 ±、区间、有效位数及单位 |
| conditions | 实验条件 | experiment | 指明模型/方法或材料配方、任务、测试设置、表格行列等；不明条件显式标未知 |
| author_conclusion | 作者结论 | paper | 忠实保留范围与限定词；观察不变成因果 |
| evidence_scope | 作者陈述的证据适用范围 | paper | 只记录作者明说的范围；Agent 对证据充分性的评判不在此字段 |
| failure_cases | 作者报告的失败情形 | paper | 不根据低分自动编造失败解释 |
| author_limitations | 作者承认的局限 | paper | 未明说不能用常识补 |
| code_availability | 是否声明提供代码 | paper | provided / not_provided；未提及用 null+not_reported |
| data_availability | 是否声明提供数据 | paper | provided / not_provided；应请求提供可记 provided，并在 note 保留条件；是否可访问不作结论 |

`data_availability` 可以记录作者明确说数据在正文/补充材料中；使用公开数据集不自动证明作者提供了研究数据。代码或数据链接只作为原文证据保留，不请求资源来验证本字段。

## 模型来源七类

| 标签 | 含义 | 必须有的依据 |
|---|---|---|
| proposed | 本文提出的新架构或模块 | 明确提出声明；仅代表作者声称 |
| structural_modification | 修改已有模型结构 | 说明基础模型与改动 |
| combination | 组合已有模型或模块 | 说明组成与组合方式 |
| finetuning_or_training_change | 微调或训练策略调整 | 明确描述调整 |
| direct_use | 直接使用已有模型 | 明确采用且描述足以支持直接使用；没写改动不等于直接使用 |
| baseline | 作为对照基线使用 | 原文明确角色 |
| undetermined | 原文不足以判断 | value 仅含该标签，状态 uncertain，说明原因；不与其他类别并用 |

多个标签各自需要证据，记录在字段 note 中说明对应关系。来源分类适用于计算、数学、物理、本构等明确模型；合成步骤、表征仪器、材料配方不自动视为模型。没有模型不是模型来源“无法判断”。

## 删除与排除

第六阶段新增独立分析字段，见 [相关性分析字典](recommendations.md)，不扩展或覆盖下面的论文事实契约；分析判断、匹配关系与阅读建议不能回填为论文事实。

第七阶段独立方案、补充问答、图文映射和视觉审阅字段见 [研究方案字典](research-proposals.md)；实验未执行、假设与新颖性未核查的状态必须保留，不扩展论文身份或复现字段。

第五阶段只增加集合、修订与导出元数据，不扩展本事实字段清单。中文导出标签见 `../assets/export-labels.json`；与本表 34 个字段一致。用户笔记、修改建议、冲突与版本字段见 [输出维护契约](output-maintenance.md)，不算论文事实。

不新增论文身份字段 DOI、arXiv ID、预印本年份、论文版本；不加入复现权重、实现细节评分。内部文件 ID、哈希、处理状态用于工程追踪，不是面向用户的论文身份信息。外部期刊评级与模型常识介绍不得写入本字典的事实记录。
