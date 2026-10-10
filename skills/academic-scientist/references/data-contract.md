# 数据契约 v0.1.0

## 记录单元

一个 paper-record 对应一篇论文的给定材料集合。`paper_id` 是内部稳定 ID，不是 DOI。`sources` 保存项目内相对路径、SHA-256、文件页数、核查过的物理页和不可读页；不把文件名或 PDF 元数据当书目信息。

`entities` 包含唯一 paper，以及按需创建的 model、experiment。多个条件的同一方法需要多个 experiment；一个模型可分模块。`assertions` 用 subject_id 关联实体，同一 subject+field 唯一。`evidence` 只引用登记过的给定材料。

`record_status=partial` 是部分提取，允许仅填选定字段；`complete` 表示所有声明实体的字段已检查和复核，不代表字段都有值或全文语义必然正确。未检查字段使用 not_checked，不能假称未报告。主文、附录是否实际覆盖须看 sources.coverage_note。

## 字段形状

每条 assertion 有 id、field、subject_id、status、value、evidence_ids、note、checked_scope、review_status。

- authors、model_inventory、model_origin 是列表；publication_year 是整数；其余为文本或规定枚举。
- result 使用原文报告形式的字符串，如 `12.3 ± 0.4 MPa`，保留单位、有效位数；不额外计算不在文献中的数值。
- supported 必须有非空值和证据；not_reported / not_applicable / not_checked 值为 null；uncertain 也为 null，模型来源例外见字典。
- 结果必须配套同 experiment 的 metric、dataset（或材料体系）、conditions；条件未知要显式说明，不能省略。
- model_inventory 的 supported 值必须精确对应记录的 model 实体；没有模型用 not_applicable 并说明检查依据。

## 来源与页码

source_kind 固定 provided_document。参考资料 URL、平台评级或个人分析不属于此 schema。PDF evidence.page 为 1 起始物理页，必须落在实际已检查页中；印刷页另存 printed_page。文本证据用 locator 标行范围，page=null。

kind=text 保存 verbatim 短片段；table 保存表头/行列的 table_transcription；figure 保存明确可见内容的 visual_transcription。保留 locator 中的节、表、图号。原始材料相对路径应以记录使用场景的项目根为基准，跨项目迁移时一起迁移 source 清单。

## 验证界限

`../scripts/validate_record.py` 检查 Schema、字段类型、来源限定、重复/悬空 ID、页码、状态以及结果上下文。

不自动验证：文件哈希是否与磁盘一致、摘录是否原文存在、原文是否支持中文概括、某模型是否真的原创、是否遗漏实验。样本准备脚本记录哈希，原文抽查和覆盖度评测另行验证。

## 演进与依赖

论文事实 Schema 保持 v0.1.0；第二阶段四个 Schema 为 v0.2.0；第三阶段 extraction-job v0.3.0 保存来源快照、检查范围、候选与复核历史，详见 [extraction.md](extraction.md)。第四阶段 venue-profile v0.4.0 独立保存发表平台定位与评价，字段字典和规则见 [venue-profiles.md](venue-profiles.md)。第五阶段 literature-collection v0.5.0 保存上游/当前事实、独立笔记、工作簿修改建议与修订历史，详见 [输出维护契约](output-maintenance.md)。分析 Schema 留到后续阶段。四类来源保持分离。

字段 ID 或语义变化需更新 schema_version 并提供迁移说明，不静默覆盖旧数据。第一阶段尚无既有正式用户记录。

开发环境依赖 Python 3.11+ 与 jsonschema；测试使用 unittest。第二阶段通过现有 pypdf、pypdfium2 和 Pillow 实现 PDF 接收及逐页文本/预览；批量解析不等于自动事实抽取或语义核查。
