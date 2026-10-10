# 第七阶段：一次交付三类图（v0.7.1）

## 一次工作流的结果

同一条已确认研究路线、同一份方案，默认产出：

| 文件 | 读者的问题 |
|---|---|
| overview.drawio / SVG / PNG / PDF | 整体输入、处理、核心方法、输出是什么？ |
| module_detail.drawio / SVG / PNG / PDF | 关键模块内部怎样工作，分支、接口和反馈怎样连接？ |
| experiment.drawio / SVG / PNG / PDF | 怎样准备数据、控制变量、运行对照、评价与核查？ |
| research-figures.drawio / PDF | 三页合并，统一编辑或阅读 |
| proposal.md / JSON | 详细方案、真实补充回答、段落与原文依据、三图组件映射 |

“一次”指 Agent 一次完成整个交付流程，不需要用户再要求绘制第二、第三张图；仍需先明确会改变科学内容的未知选择。绘图、渲染和审查由多个工具步骤完成，不是一个模型调用保证可发表质量。单图 PNG 只作预览，可编辑源是 draw.io。

## 先统一语义，再拆三个视图

1. 从已审阅方案选择整体模块，并在 canonical nodes/edges 中只定义一次。同一 ID 在各图复用文字、状态和段落引用，不在各视图独立复制事实。
2. 选一个概览中的关键模块为 module_detail.focus_id，以 parent_id 表示其内部步骤。模型结构已知时才画内部模型；未知时画已确定的功能、工具和接口，保留未知，不自行增加层数、维度或模型版本。
3. 实验图标明训练/验证/测试隔离、对照与控制变量、停止条件、核查和报告。图中步骤都是待验证设计，除非明确标为给定文献做法；画出步骤不授权执行实验。
4. 概览保持简洁；详图展开核心步骤；实验图按并行流程或阶段排列。跨图组件改变时重新复核整个方案与三图，不直接回写论文事实。

## 字段字典

契约：[figure-set.schema.json](../schemas/figure-set.schema.json)。它作为 plan.figure_set 的可选字段嵌入 [research-proposal](../schemas/research-proposal.schema.json) 和 [proposal-run](../schemas/proposal-run.schema.json)。外层历史 schema_version 仍为 0.7.0，扩展内为 0.7.1；旧单图方案不强行迁移。

| 字段 | 约束 |
|---|---|
| nodes | 唯一 id、label、kind、phase、statement_refs、parent_id、shape；kind/phase/证据规则继承方案契约；parent_id 为组件关系，非排版分组 |
| shape | process 圆角框、decision 判断菱形、data 数据圆柱、artifact 文件；形状不能替代来源状态 |
| edges | id/source/target/relation/label/statement_refs；relation 为 data/control/feedback/update/reference；reference 必须引用文献已有做法段落 |
| views | 恰好 overview、module_detail、experiment，不允许缺图或额外不明视图 |
| view | title、purpose、focus_id、node_ids、edge_ids、canvas、positions、routes、groups |
| positions | 每个选中节点的全局 x/y/width/height；显式坐标，支持多行和分支；不存在固定8节点上限 |
| routes | 每条选中边的 source_port/target_port（上下左右）、waypoints、label_box 或 null；折线路径与端点明确 |
| groups | id、label、node_ids、bounds；不重叠分组，导出原生父子图元，节点几何转换为组内相对坐标 |

每图必须连通，图中边的两个端点都在该图；模块详图必须展开 overview 中 focus_id 的至少一个子组件。禁止引用不存在的段落、循环 parent、节点重叠、连线穿节点/标签、画布越界。graph 与 figure_set 使用相同节点 ID 时其语义必须一致。检查不能自动判断文本语义正确，Agent 仍须对照原文、用户目标和方案逐图审查。

canvas 顶部110、底部85像素为标题和图例保留。默认字体 Microsoft YaHei，节点25、标题32、组标题23、线条注释21像素，最小节点160×80。过长标签报错；应精炼文字或扩大模块，不通过无限缩字解决。支持本生成器的四种形状、端口、分组和正交折线；任意 draw.io 形状、嵌套视觉分组、公式排版和自动网络布局不在当前内置渲染范围。

## 连线布局与最终 XML 检查（2026-10-09 修订）

1. 先列出 source/target、方向及关系含义，再安排位置。主路径、并行分支与反馈分别留出通道；同侧扇入/扇出宜分开端口。复杂程度超过一张图的承载能力时调整布局或拆视图，不删改科学关系来消除交叉。
2. 将边界端口写入 exitX/exitY、entryX/entryY，设置 exitPerimeter=0、entryPerimeter=0；原生 mxGeometry/Array(points) 写入折点，noEdgeStyle=1 固定折线。边采用页面坐标，节点允许分组相对坐标。不要只依靠 edgeStyle=orthogonalEdgeStyle 自动避障，也不要从方框中心起线。
3. 连线不得穿过节点（包括自己的起点/终点内部）、标题或标签；与无关方框通常至少留8像素。分支保持可追踪，优先消除交叉与共线重叠。共用线段只有在含义明确、视觉可辨且实际审阅记录说明时才能保留；交叉点不自动代表连接点。不能把实线改成虚线来掩盖穿框问题，实虚线只编码关系含义。
4. 最终 XML 是可编辑图的源。SVG 路径从其端口/折点解析，不另写 connections 数组；历史 preview_points 仅作一致性断言。检查每条线的方向与端点，不能用“SVG 看起来正常”代替 XML 检查。

对三张独立文件及三页总文件执行（输出保存到本次工作目录）：

```powershell
python -B -X utf8 "<SKILL>/scripts/drawio_routes.py" "实际目录/overview.drawio" --output "实际检查目录/overview-routes.json"
```

同样检查 module_detail、experiment、research-figures。脚本要求未压缩 XML、固定端口和正交折线；发现穿框、隐式路由、失配缓存、越界等则失败；交叉和共享/重叠线段单独列为 warnings，必须人工查看。默认8像素间距；生成器和整组审查另有不可绕过的穿框检查。零错误仍不等于没有语义歧义或原生兼容已验证。

内置预览只支持本技能的有限图形/文字样式，不是任意 draw.io 渲染器；有弧线、压缩页面或不支持的相对几何时不能静默回退到中心连线。保留来源并转换到可检查布局，或明确补做原生渲染。手工/其他 Agent 生成的图也执行同一最终 XML 检查。新检查不回写历史审查；旧图重新交付需另建修订版。

标准整组交付仍使用下方 export-set/review-figure-set/figure-set-status。自定义 schema/manifest、手写 review 或仅有哈希不具备同等验收效力。若任务仅为修复已有图的布局，应单列 layout-only 审查和原始语义对比，不伪造标准 proposal 状态，不声称科学方案已经通过。

## 导出、渲染、复核

1. 将完整 figure_set 放入 plan，submit/review；同时检查训练、验证、测试数据路径及未知状态。
2. 调用 research_proposals.py 的 export-set（输入 `{}`）。它先检查所有输出，再保存三图、三页总文件、方案和 manifest；有同名人工编辑则拒绝覆盖。有 figure_set 时普通 export 也进入三图分支，旧方案 export 保持原行为。
3. 使用当前环境已有的渲染器。提供的 [render_figure_set.mjs](../scripts/render_figure_set.mjs) 使用现有 Playwright 与 Chrome，一次渲染三图为 PNG、单页180mm宽 PDF、纸面截图与源文件哈希记录。运行示例：

```powershell
node "<SKILL>/scripts/render_figure_set.mjs" --root "<ROOT>" --folder "work/my-proposal/exports/实际导出目录" --cycle-folder "work/my-review/cycle-1" --runtime-package "<现有运行库的绝对解析锚点>" --browser "<已定位浏览器的绝对路径>"
```

示例依赖路径仅说明当前项目已有环境，其他环境先检查实际能力，不直接安装软件。所有截图和本次临时浏览器目录均保存在给定内部工作根目录；浏览器关闭后清理本次随机临时目录，清理结果保存在temporary-files.json。每轮使用新 cycle-folder；禁止用重复文件覆盖假装新审查。

4. 三图每轮均实际查看，至少三轮截图→审查→修正/复查。九区覆盖标题、核心内容、四周边界、图例等，记录真实问题，没有问题就如实写无新增问题。将第三轮 PNG/PDF/纸面截图复制到导出目录，按 overview→module_detail→experiment 合并三页 PDF，再查看 PDF 重渲染图。
5. 使用 review-figure-set 保存整组证据。请求含 expected_revision、reason、export_folder、reviewer、combined_pdf、views。views 必須三项齐全，每项包含 cycles（恰好三次 screenshot、render_record、source_drawio、source_svg、note）、checks（semantics/readability/connectors/paper_scale 均 true）、png、pdf、paper_scale。路径均相对工作根目录。
6. 最后运行 figure-set-status，输入 `{"export_folder":"实际相对目录"}`。只有整组 delivery_ready=true 才报告完成。修改任何一图、合并文件、预览、审查证据或上游方案均需重新核查；不允许仅核对概览就宣称三图通过。

审查契约：[figure-set-review.schema.json](../schemas/figure-set-review.schema.json)。前三轮可对应不同源版本，最后一轮必须是当前图。脚本绑定真实源、SVG、截图与 PDF 哈希，检查 PNG 可解码、各视图 PDF 单页、合并 PDF 三页及页内容一致；不能证明审阅者确实读懂图，也不能替代独立人工验收。

本地 SVG 是从 draw.io XML 解析的受限预览，native_drawio_render_verified 始终 false。若使用 academic-figures-drawer 静态工具，其质量检查器不解析原生组内相对坐标；可针对从原图解析出的绝对坐标副本检查几何，原文件另做 XML 结构检查。不得将已知误报悄悄计为通过，须记录变换和检查范围。

## 修改与恢复

旧三图、旧单图和历史审查均保留。任意手改导致绑定失效时，先保留用户版本；科学语义修改回到方案，布局修改同步 positions/routes 并新建导出版本。不能自动将三页或独立文件中的一份修改静默合并到其他文件。

本功能是第七阶段扩展，不启动第八阶段，也不自动运行研究实验。原文不足以画清内部方法时，需要询问或标出未知，不能用图形细节填补证据空缺。
