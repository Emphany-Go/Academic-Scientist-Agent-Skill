# 文献接收、解析与恢复

第二阶段仅做给定 PDF 的本地接收、逐页文字与页面预览，不做第三阶段的事实抽取、自动语义阅读、结构化表格或 OCR。

## 工具与边界

- 使用当前已有 pypdf 提取文本，pypdfium2 渲染页面；不联网上传文献，不下载新模型。
- 每页保留 1 起始物理页码、原始提取文本、PNG 预览、哈希、问题及处理状态。
- 少于 40 个非首尾空白字符的文本页被标记 needs_visual_review。这是提示，不是扫描件的确定分类：可能是空白页、图片页或提取失败。
- 替换字符或 NUL 标记 text_suspect；未检测到这些字符不代表文字正确。字体映射错误可能仍产生正常 Unicode 字符，如第一阶段的 Pérez 乱码。
- 所有页面 semantic_review=not_started。即使 parsed_text，也只能说“已生成逐页文本与预览”，不能说“已读完论文”。
- tables=not_structured；figures=page_preview_only。图表以原页面保留，第三阶段需要对照原图，不凭线性文本猜行列。
- 缺 OCR/更高级解析能力时按规则标记；确需安装工具先向用户确认。加密 PDF 为 password_required，本阶段不保存或处理密码。

## 命令

```powershell
python -B -X utf8 "<SKILL>/scripts/paper_library.py" --root "<ROOT>" add --input "<ROOT>/files.json"
```

所有 JSON 路径使用实际文件路径，不把示例路径当成存在的文件。JSON 中 Windows 反斜杠需要转义，或使用 `/`。

| action | 输入与行为 |
|---|---|
| add | paths 为明确选中的 PDF 路径列表；role 默认 main；supplement 要带已登记 parent_doc_id |
| parse | doc_ids 省略则处理已登记论文；max_pages 为本次每篇最多新处理页数；reparse 默认 false |
| show | 查看清单与缺附件记录，不解析、不改变已完成状态 |
| expect | parent_doc_id、label；记录用户或已检查原文明确要求而未提供的补充材料，不凭常识自动推断有附件 |
| link | expectation_id、doc_id；将已登记的附件关联到缺失记录；不覆盖已有不同附件 |

add 示例：

```json
{"paths":["<用户选定论文的绝对路径>.pdf"]}
```

parse 示例：

```json
{"max_pages": 2, "reparse": false}
```

## 内容身份与版本

以完整 SHA-256 为内部文档 ID。相同内容换文件名只增加来源路径，不重复复制；相同路径的文件内容改变会登记为新文档。该 ID 不是新增的论文身份展示字段，也不把 PDF 元数据当正式发表信息。

原始文献不修改；项目工作目录内保存 source.pdf 副本。每次解析先校验副本哈希；不一致时拒绝解析并报告，不静默覆盖恢复。正文与补充文件独立 ID，关联保存在 roles/expectations；缺附件不阻止已有正文解析，但后续不能假称材料完整。

## 状态与继续处理

| 文档状态 | 含义 |
|---|---|
| registered | 已保存副本，未解析 |
| processing | 正在处理或上次在处理中断 |
| partial | 本次达到 max_pages，仍有页未处理 |
| parsed_text | 全部页完成文本及预览生成，未触发当前质量启发规则；没有完成语义核查 |
| review_required | 已尝试全部页，但有稀疏/可疑文本或单页失败 |
| failed | 文档损坏、源文件完整性问题或解析器异常；原因保存 |
| password_required | 文件加密，等待可读副本 |

再次 parse 时读取逐页检查点，校验文本与预览哈希；完整页复用、缺失/损坏缓存页重建、失败页再次尝试一次。needs_visual_review 页面不会因重复运行自动被称为已 OCR。

reparse=true 明确新建 attempt，保留旧解析结果；解析器版本或配置发生改变时要求显式 reparse。正常恢复无需该参数。

每篇失败独立保存，批次继续处理其他文件；命令返回结果列表。退出码 1 表示至少一个登记/解析失败或需要密码，不能忽略已完成结果。review_required 和 partial 是可继续处理状态，必须读取结果列表而非仅依赖退出码。

## 存储与阶段三接口

工作目录下 `library/manifest.json` 存文档和附件清单；`library/documents/<sha256>/source.pdf` 存副本；`attempt-N/parse.json` 与 `page-N.txt/png` 存解析检查点和材料。

后续抽取应从 manifest 找 active_parse，结合逐页 text 与 PNG 查证。原始 source ID、文件哈希和物理页码传递到事实记录。不能直接把解析过的页填入第一阶段 sources.inspected_pages；只有 Agent/用户实际检查原文后才能登记为已核查。

Schema：[文献清单](../schemas/library-manifest.schema.json)、[逐页解析记录](../schemas/document-parse.schema.json)。
