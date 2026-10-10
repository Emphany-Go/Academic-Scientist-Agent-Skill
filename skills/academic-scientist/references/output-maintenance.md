# 第五阶段：输出与维护

## 使用时机

将第三阶段已复核的论文事实汇总成 Excel 与逐篇 Markdown，接收用户直接修改的工作簿，增量同步新论文或新抽取，并保留历史。入口为 `scripts/literature_output.py`；XLSX 渲染为 `scripts/workbook.mjs`。论文事实仍使用 v0.1.0；集合与修订契约为 [literature-collection.schema.json](../schemas/literature-collection.schema.json)。

用户已经选择直接编辑事实单元格及独立笔记栏，不再要求填写单独的修订表。事实修改并不自动成为真值。结构化记录是事实来源；工作簿、Markdown 是带版本的可编辑输出。

## 工作簿与阅读卡

| 页面 | 内容 | 可以直接修改 |
|---|---|---|
| 论文总览 | 标题、作者、正式发表年份、期刊或会议、覆盖、身份字段状态与证据 | 四项身份值、个人笔记 |
| 论文事实 | 每个论文/模型/实验实体的其余字段，状态、证据编号、说明 | 内容列 |
| 原文证据 | 来源文件、PDF 物理页码、原文定位、短摘录或图表转录 | 仅阅读 |
| 平台认知 | 官方研究领域、评价体系/版本/学科、来源、论文关联 | 仅阅读；更新走第四阶段 |
| 修订记录 | 原值、修改建议、处理状态与核查说明 | 仅阅读 |
| 使用说明 | 编辑、数组、清空、版本和来源规则 | 仅阅读 |

浅黄色内容区可编辑。可以筛选、整行排序；第一列稳定 ID 用于识别，不能改动。不得删除行、改表头/页名或新增事实行；若需新增模型、实验或证据，走第三阶段。表格不是自由排版文档，导入会明确拒绝这些结构变化，原文件保留。

作者、模型清单和模型来源标签用单元格内换行分项；年份为整数。结果字符串保留原单位、有效位数和条件，不从字符串自动转换单位。未检查、无法确认、未报告、不适用各自保留状态，未知值不填 0。

每篇 Markdown 含全部适用字段及缺失状态、原记录说明、证据、独立笔记；不自动撰写推荐或研究方案。Markdown 自由修改可保留在旧文件内，但不自动解析其自然语言回填事实。需同步的事实修改走 Excel，或由 Agent 回到第三阶段核查。

## 集合与修订字段字典

| 字段 | 含义 |
|---|---|
| schema_version / revision / saved_at / reason | v0.5.0；不可覆盖的集合版本；实际保存时间；变更理由 |
| papers[paper_id].record | 当前生效且经过复核的事实记录，不能混入笔记或平台评价 |
| upstream_record | 上次导入的第三阶段记录原貌，作为下次增量合并的基准 |
| record_path / record_sha256 | 上游事实 JSON 的项目相对路径和内容哈希 |
| source_files | 文献 source_id 到项目相对原文路径的映射；同步、采纳事实修改时核对原文哈希 |
| notes | 每篇论文独立笔记；无原文证据的个人观点只能进入此处 |
| changes[].id / kind / paper_id / key / field | 修订 ID；fact/note/upstream；归属论文、字段稳定键和字段名称 |
| base / current / proposed | 导出原值、导入时现值、用户修改值；upstream 冲突记录保存三份文献记录的摘要哈希 |
| base_assertion / current_assertion | 字段完整状态与证据快照；即使值没变但证据变了，也需重新核查 |
| status | pending 待原文核查；conflict 有并行修改；accepted 已处理；rejected 不采纳且保留建议 |
| import_id / export_id | 返回工作簿及原导出关联；整份上游冲突处理不来自 Excel，二者为空 |
| reviewer / reviewed_at / review_note / decision_ref | 审阅者、审阅时间、依据与真实消息/核查日志引用；不伪造用户批准 |
| imports | 已接收的工作簿与导出组合标识，同一组合重复导入不追加修订 |
| venues | 第四阶段官方视图快照与独立关联，不写回论文事实 |

导出目录的 `baseline.json` 保存集合摘要、六页原始值及可编辑单元格到字段的映射；目录 export_id 是该对象摘要的前 24 位。导入时校验基线未变，使用页面第一列的 ID 比较整行排序后的值。`workbook-seal.json` 保存 XLSX、基线与生成器哈希，用于拒绝覆盖改过的工作簿。

## 操作顺序

1. `show` 恢复集合；先核对现有版本，不重新初始化。`sync` 读取第三阶段已复核导出，校验结构、原文路径与哈希；原数据不修改。文献 ID 不得复用于不同主文。
2. 如需平台资料，用 `venues` 从第四阶段工作目录读取官方视图及关联。默认 latest_verified/official_only；未知仍显示“尚未查阅到相关官方评级”。事实更新后旧关联降为 unresolved，重新核对再关联。
3. `prepare` 写不可覆盖的基线、五篇或更多 Markdown 与索引；随后调用 `workbook.mjs` 生成 XLSX。按数据和样式变化检查实际预览；不能把程序导出成功当排版合格。
4. 收到修改版 XLSX 后，用原 export_id 执行 `import-edits`。先检查结构与只读内容，再按“导出基线/当前记录/用户修改”比较；完整返回文件按哈希归档。笔记无冲突自动合并；事实始终 pending 或 conflict，暂不改生效值。
5. 逐项回看给出的原文。用户可把页码、原句和修改理由写在个人笔记里，Agent 负责实际核查。无证据不采纳为事实；解释原因或保留为笔记。存在冲突必须先让用户明确选择，并记录实际答复引用，不能把超时当批准。
6. 用 `review` 采纳或拒绝单项。采纳需要完整 reviewed_record，与当前记录只允许目标事实不同，使用已有证据、相同来源/实体/覆盖范围，目标标 agent_checked。脚本核查机械约束，宿主 Agent 对语义与原文一致性负责；不能声称独立人工验收。
7. 新证据、增加实体或把未检查升级为“未报告”时，先回第三阶段完成检查与审阅，再 `sync`。不能仅靠 Excel 清空值或第五阶段审阅绕过全文覆盖要求。旧建议可记录为已处理而拒绝重复应用，理由注明它已由第三阶段修订落实。
8. 再次 `prepare` 与渲染得到新版本；旧工作簿/Markdown/JSON 保留。新导出继承已合并的事实与笔记；用户自改的格式、工作表结构、Markdown 自由文字保留在原文件，不自动搬进新版。

上游更新：未改变的论文按哈希复用，新增/变化论文增量同步。上游字段和已采纳用户修订互不冲突时三方合并；冲突时整个 sync 批次不落盘，明确列出冲突，其他无关论文可拆批继续。用户选择保留本地或采用新抽取后，`resolve-upstream` 保存该选择及消息引用、更新上游基准；旧快照仍在。需要逐字段混合结果时先由 Agent 形成已核查记录，不擅自整篇取舍。

## CLI 与请求

在内部工作根目录ROOT执行；实际使用时替换脚本、根目录与集合目录。所有输入路径相对 `--root`，不允许逃逸。`source_root` 是第三阶段工作目录，用于解析记录内的文献相对路径。

```powershell
python -B -X utf8 "<SKILL>/scripts/literature_output.py" --root "." --collection work/my-literature sync --input requests/sync.json
python -B -X utf8 "<SKILL>/scripts/literature_output.py" --root "." --collection work/my-literature prepare --input requests/empty.json
```

`empty.json` 内容为 `{}`。新建集合的 sync 示例：

```json
{"expected_revision":0,"reason":"导入已复核记录","records":[{"record_path":"work/reading/extraction/P01/exports/r000004/record.json","source_root":"work/reading"}]}
```

| 动作 | 除通用 expected_revision、reason 外的参数 |
|---|---|
| show / prepare | 不需要通用参数；payload 为 {} |
| sync | records 数组；每项 record_path、source_root |
| venues | entries 数组；每项 workspace、view_request（第四阶段参数）、link_paths（相对 workspace） |
| import-edits | export_id、workbook_path |
| review | change_id、decision=accept/reject、reviewer、review_note、decision_ref；采纳事实另需 reviewed_record_path；conflict 另需 conflict_resolution_ref |
| resolve-upstream | record_path、source_root、choice=keep_local/use_incoming、reviewer、conflict_resolution_ref |

拒绝也要写清依据；conflict_resolution_ref 和 decision_ref 必须指向真实用户消息或可回查核查记录。此引用字段的结构存在不等于程序已经验证科学结论。

## XLSX 运行依赖与恢复

XLSX 使用已有 Node 与 `@oai/artifact-tool`；优先查询宿主 `load_workspace_dependencies`，不可用时检查已有 bundled runtime 缓存。仅在项目内建立指向运行库的 node_modules junction/symlink，不复制修改依赖、不全局安装。依赖不可用先报告并确认，JSON/Markdown 和既有版本可继续使用。

`workbook.mjs` 接受基线绝对/相对路径及含 node_modules 的运行目录，不包含本机硬编码路径：

```powershell
& "<已有 node 可执行文件>" "<SKILL>/scripts/workbook.mjs" "<prepare 返回的 baseline.json>" "<项目内运行目录>"
```

生成器输出同目录的 `literature.xlsx`、渲染预览、内容检查与哈希封印。已有输出被改动则拒绝覆盖；先导入用户修改、创建新集合版本再输出。生成器变化而基线相同时也拒绝覆盖，需显式新版本。中断时已有 Markdown 可补齐；XLSX 缺失可重试；存在无封印 XLSX 则保留并检查，不直接删除。

导入仅读取 OOXML 值，不执行公式或外链。发现公式/错误单元格、重复 ID、删除行或只读项修改会拒绝该次导入，原返回文件不修改；请用户恢复结构，或从新导出复制待改内容。未修改的工作簿也可导入；再次导入同一文件幂等。

验证文件状态、结构、哈希与合并逻辑，不代表 Excel/WPS 全版本兼容性或文献全文语义准确率。真实用户编辑体验另行验收。
