# V0.1：安装后的项目、环境与文件保留

## 路径约定

先确定用户指定的研究项目；未指定且无法从当前工作目录确定时询问。设 SKILL 为当前 SKILL.md 的父目录，PROJECT 为研究项目，ROOT 为 `PROJECT/.academic-scientist`。所有 `scripts/...` 均相对于 SKILL 解析；示例不是要求在安装目录中生成文件。

先运行 `python -B -X utf8 "<SKILL>/scripts/project_workspace.py" --project <PROJECT> init`，记录返回的 workspace_root。旧任务直接按原root恢复；不自动搬迁旧研究或套用历史用户答案。安装目录保持只读，Python用-B避免写入pycache。

之后第二至第七阶段脚本的 `--root`/`--workspace` 都使用 ROOT；会话、library、extraction、collection、venues、analysis、proposal、requests、review都存于其中。阶段参考中的“工作目录”均指ROOT；请求里的相对路径保持以ROOT为基准。

表层只放阅读入口、研究档案、文献整理.xlsx、阅读建议.md、研究方案.md、论文阅读卡/和流程图/。这些文件按完成阶段出现，不预先填空白结果冒充完成。`.academic-scientist`是内部目录命名约定，不保证各操作系统文件管理器都会自动隐藏。

## 环境检查

运行 `scripts/check_environment.py`；如已定位Node、浏览器和现有运行库，可传 `--node <node可执行文件>`、`--runtime-package <已有运行库的package.json解析锚点>`、`--browser <Chrome或兼容Chromium可执行文件>`。输出放 `ROOT/requests/environment.json`。解析锚点可不实际存在，但其父目录必须能解析相应Node包。

| 能力 | 依赖 |
|---|---|
| 会话/结构与状态校验 | Python 3.10+、jsonschema |
| 给定PDF解析与页面检查 | pypdf、pypdfium2、Pillow |
| Excel渲染 | Node及宿主已有@oai/artifact-tool；用load_workspace_dependencies发现（如可用） |
| 图形PNG/PDF | Node、Playwright、已有Chrome/Chromium |
| 论文语义阅读、官方检索 | Codex的阅读/视觉/联网能力，不是上述脚本自主完成 |

检查脚本不安装依赖，不证明渲染或事实正确。缺项明确报告受影响能力，先询问安装或替代方案；其余已授权工作继续。Python依赖清单在skill的requirements.txt；Node组件不随包分发，不把Codex运行库当成可随意redistribute的开源依赖。缺少artifact-tool时V0.1不能生成新的XLSX，仍可保留JSON/Markdown，不把CSV当成已完成Excel。

## 发布成果

先完成对应阶段的review/status，图形完成整组三图审查。再向 `scripts/project_workspace.py --project <PROJECT> publish --input <请求JSON实际路径>` 提交明确文件列表。该命令只做安全复制/记录，不替代业务和证据验收。

```json
{"artifacts":[
  {"source":"analysis/my-reading/exports/实际版本/reading-guide.md","target":"阅读建议.md","kind":"recommendations"},
  {"source":"proposal/my-proposal/exports/实际版本/proposal.md","target":"研究方案.md","kind":"proposal"},
  {"source":"proposal/my-proposal/exports/实际版本/research-figures.drawio","target":"流程图/research-figures.drawio","kind":"figure"}
]}
```

source相对于ROOT；target相对于PROJECT。各类目标限制为：workbook→文献整理.xlsx；recommendations→阅读建议.md；proposal→研究方案.md；research_profile→研究档案.md；figure→流程图/下单层drawio/svg/png/pdf；card→论文阅读卡/下单层md/json。逐篇卡可直接发布；不要复制带有失效papers/相对链接的内部INDEX，表层入口会自动列出卡片。

workbook还必须携带 prepare 返回的 `export_id` 和 ROOT 内 `collection`路径；源必须是 `collection/exports/<export_id>/literature.xlsx`，baseline/seal一致才能发布。发布不移动原件；旧的未被用户修改成果留存到内部deliveries/history。任何已修改的表层文件或阅读入口都拒绝覆盖，先让用户明确如何保留/合并，不把同名文件当缓存删除。

用户直接编辑表层Excel后，运行 `collect-edits`（同一脚本），保存到内部inbox并取得原export_id、collection和workbook_path。将这些字段连同最新expected_revision/reason传给原第五阶段import-edits；后续事实复核/冲突处理规则不变。收集操作不采纳任何事实、不替换用户Excel。合并完成后若需要换成新表，须先确认旧编辑稿的归档方式；V0.1不会静默替换。

## 数据字典与保留

契约：[项目状态](../schemas/project-workspace.schema.json)、[发布请求](../schemas/project-publish.schema.json)。发布版本V0.1不改变各阶段原Schema版本。

| 字段 | 含义 |
|---|---|
| schema_version/release/revision | 项目交付索引契约、发布版本、递增索引版本 |
| files[target] | source/target/kind/sha256以及工作簿原export_id/collection；目标文件到内部正式导出的对应 |
| index_sha256 | 自动阅读入口的最后生成哈希，用于保护用户改写 |
| artifacts | 本次明确选择且已业务复核的成果列表；不会扫描目录自动复制所有文件 |

长期保留论文原文、证据、问答、状态版本、Excel基线/回读、图源、实际审阅截图/记录和交付索引。审图三轮截图有验证用途，不当临时垃圾删除。暂不自动裁剪历史，避免破坏证据引用。

新图形渲染只在当前cycle内创建随机 `.render-temp-*`，浏览器关闭后清理自己本次创建的目录；PNG/PDF/HTML/render.json保留，temporary-files.json记录清理结果。失败或文件占用如实报告，先恢复再处理；不扫描删除旧profile、旧run或用户目录。历史评测文件仍在开发项目中，未被正式版迁移/删除。

当前项目发布是逐文件写入；正常冲突在写入前检查。如磁盘异常中断，保留当前文件、按project.json及内部deliveries核对后恢复，不把部分写入宣称整组完成。
