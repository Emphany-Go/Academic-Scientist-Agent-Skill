# 第四阶段：发表平台认知卡

## 用途与边界

为用户建立期刊/会议的基本认知：官方研究领域、适用的 JCR/中科院/CCF 评价、具体版本和学科、查询日期、来源与未核实项。认知卡与论文事实分开；不根据平台等级评价单篇论文，也不让等级直接决定阅读排序。

由宿主 Agent 使用可用的网页工具检索与核查，`scripts/venue_cards.py` 保存、校验与导出。脚本不自动爬取网站，不包含付费数据库账号，不推断未知等级，也不改变第一至三阶段的事实 Schema 或文件。

## 已确认的展示与来源规则

用户于 2026-10-03 明确选择：评价年份展示最新可核实版本；官方评级无法查询时显示“尚未查阅到相关官方评级”，不展示或检索第三方信息。默认策略保存在 [venue-policy.json](../assets/venue-policy.json)，由运行脚本读取，不再重复询问。

- `time_basis=latest_verified`：每个评价体系展示已保存官方证据中发行年最新的已核实版本，同版已查学科全部并列。旧版只留在历史记录中，不为了补齐某学科混入旧版更优值。
- 已知较新版本尚未核实时，单独显示未知；旧版仍写明其真实发行年，不能称为当前最新版。同一发行年有多个正式修订时，Agent 须核对修订先后，将被取代的版本留在历史 revision；无法确定则记录冲突，不擅自选取。
- `source_policy=official_only`：只查询官方研究范围和评级机构原始资料。检索应限定相关官方域名，不检索第三方网站，也不从出版社转述、搜索摘要或记忆填写评级。
- 官方评级未取得时，value=null，明确显示“尚未查阅到相关官方评级”；不适用项单独说明。未知不等于未收录、低等级或不存在官方评级。
- `publication_year` / `both` 保留为明确请求历史比较时的接口能力，不是当前默认。历史口径严格按发行年匹配，不沿用相邻年。
- 第三方数据不允许新录入；含第三方数据的旧卡也拒绝 show/view/export/link，不输出原始值、备注或来源链接。先保留旧档，再由 Agent 按官方证据另建干净版本，不静默改写历史。

策略文件字段：time_basis（默认时间视图）、source_policy（固定 official_only）、search_third_party（固定 false）、missing_rating_text（缺失提示）、confirmed_on 与 decision_source（用户决策依据）。脚本本身不联网；检索范围由宿主 Agent 遵守上述规则，单元测试不能替代对宿主实际检索行为的审计。

## 操作顺序

1. 从论文事实记录读取 supported 且已复核的 venue 字段。若未知，保留关联 unresolved；可以单独介绍用户指定的平台，但不能联网补回论文事实。
2. 核对官方名称、平台种类、主页和别名。Polymer 与 Polymers 是不同名称；简称、改名、同名平台需要来源支持。期刊、会议主会与 workshop 不能合并。
3. 读取官方 Aims and Scope、学会刊物介绍或会议征稿范围，用简明中文概括研究主题。不要照搬宣传性“顶级/领先”等形容词作为独立评价。定位存在局部矛盾时写清具体范围；不能擅自决定冲突内容。
4. 分别查询评级机构提供的正式目录/记录，确认正式版或勘误版，而非公示版。保存体系、发行版本/年份、指标年（明确可知时）、学科、类别层级及证据。
5. 对字段与来源作逐项核对后 `put` 保存版本。接口校验不是独立语义验收；verified 只表示 Agent 已按来源核查。
6. 按用户确认的策略 `view`/`export`，输出 JSON 和可编辑 Markdown 卡片；用 `link` 保存论文与平台关联。无法核实的评级不阻断正文整理或其他平台处理。

遇访问受限，记录实际结果（例如 403、502、内容无法读取），不一概声称“需登录”或“未收录”。不登录、购买、安装依赖或调用付费 API，除非另获用户授权。用户已授权提供的官方截图/导出可纳入；查看原件并确认机构、平台、版本、类别与时间完整，保存项目内副本和哈希。

## 评价字段字典

数据结构见 [venue-profile.schema.json](../schemas/venue-profile.schema.json)。`schema_version=0.4.0`，`source_kind=external_venue_profile`。

| 字段 | 语义与核查要求 |
|---|---|
| venue_id / name / aliases / kind / homepage | 平台稳定内部 ID、正式名称、有依据别名、平台种类及官方主页；不是新增论文身份字段 |
| identity / positioning | 各自保存 status、text、source_ids、review_note；未核实则 text=null |
| sources | URL、页面标题、authority、评级 system、实际 access、retrieved_on、短原文 excerpt、具体 locator、说明；可选项目内 artifact_path 与 SHA-256 |
| ratings.system | JCR、CAS（本项目指中科院分区）、CCF；不把索引中的 Chemical Abstracts Service 当作中科院分区 |
| edition / release_year | 官方发行版本名称和年份；旧页面发布日期、抓取日期不能当评价年份 |
| metric_year / period_note | 指标所属年与时间解释；不能把 JCR 发行年机械减一后冒称核实，无法确定用 null |
| category / category_level | JCR 的 jcr_category；中科院 major/minor；CCF 的 ccf_area；未知用 unknown。全部已查类别并列，不只选最好看的分区 |
| value | JCR Q1–Q4；中科院 1区–4区；CCF A–C；体系不能互换 |
| status | 当前可用 verified、unverified、conflicting、not_applicable；后三者 value=null。Schema 中 third_party 仅用于识别旧格式，当前语义校验拒绝该值 |
| coverage | all_categories_checked / selected_categories / unknown；标全部须确实核查完整分类，不以查到一项代替 |
| applies_to | journal / full_regular_papers / unknown；主会等级不自动给 workshop、短文等论文类型 |
| checked_on / review_note | 实际查询核查日期与判断依据；不填写未来日期，不把缓存读取日当新的查询日 |

来源 authority 当前仅允许 venue_official、rating_official；Schema 保留 third_party 旧格式标识，但语义校验拒绝录入与展示。access 为 read、search_only、blocked 或 user_supplied。搜索片段只用于找入口，不能单凭片段接受正式等级。评级 verified 需要对应发行机构的已读来源；出版社自己的宣传或指标转述不能充当评级机构原始记录。

现有验证器检查 CCF、Clarivate、中科院分区表的机构域名范围，拒绝诸如 `clarivate.com.other-site.org` 的冒充域名。但域名匹配不能证明该网页支持某个等级，截图也不能仅凭填写官方 URL 就认定真伪，仍需 Agent 核对。

同一体系、版本、学科出现不同值，合并为 conflicting，保留各来源与原因；不在同一行悄悄选一个。评级字段中的 not_applicable 不是“档次低/未收录”；只能用于体系明确不适用的情况并说明理由。

## 接口与保存

在 skill 目录执行：

```powershell
python -B -X utf8 scripts/venue_cards.py --root "<ROOT>" put --input requests/venue-put.json
python -B -X utf8 scripts/venue_cards.py --root "<ROOT>" show --input requests/venue-show.json
python -B -X utf8 scripts/venue_cards.py --root "<ROOT>" export --input requests/venue-view.json
```

`--input` 为工作目录内相对 UTF-8 JSON 路径；Python 对应 `execute(root, action, payload)`。所有数据写入指定工作目录。

| 动作 | payload |
|---|---|
| put | card 完整对象、expected_revision（新建为0）、as_of（当前用户环境日期）、reason |
| show | venue_id，可选 revision；无 revision 读取最新版，官方历史即使来源不可访问仍可查看，含第三方数据则拒绝输出 |
| view / export | venue_id、as_of、max_age_days；time_basis/source_policy 省略时读取已确认默认；历史或双时点另需 publication_year，可选 revision |
| link | record_path（相对工作目录）、venue_id、note |

请求形状示例（省略已保存的默认策略）：

```json
{"venue_id":"example-journal","as_of":"2026-10-03","max_age_days":30}
```

缓存有效期作为显式参数传入；30 天可用于常规阅读的技术示例，关系到实际投稿/评价的任务要当次重新查询。超过时限仍可查看历史值，但明确标“需重新查询”，不能当作刚核实的最新值。缓存年龄取相关来源与记录中的最早日期，不能仅改卡片日期把旧证据变新。

```text
研究工作目录/
  venues/<venue_id>/revisions/000001.json ...
  venues/<venue_id>/exports/r000001-<展示参数哈希>/card.json
  venues/<venue_id>/exports/r000001-<展示参数哈希>/card.md
  venue-links/<关联内容哈希>.json
```

更新使用最新 expected_revision，原版本保留；同内容复用不增加版本。导出按版本、日期与展示参数保存，重试可补齐中断产物；手工改过的导出不覆盖。完整人工修改合并仍属第五阶段。

关联只在论文已有 venue 事实与已核实名称/别名严格匹配时标 matched，否则 unresolved。link 文件保存原记录路径/哈希和平台版本，不改写论文、不自动赋予单篇论文等级。改名尚未核实、事实字段未提取时保持待确认；不得为了提高关联率自行扩充别名。

## 官方检索入口

- [CCF 正式推荐目录](https://www.ccf.org.cn/Academic_Evaluation/By_category/)：检查版本、领域、会议/期刊和适用论文类型；平台评价不能代替单篇成果评价。
- [中科院期刊分区表](https://www.fenqubiao.com/)：分别保留大类/小类及官方版本。
- [Journal Citation Reports](https://jcr.clarivate.com/)：核对具体期刊、学科、版本和指标时间。发行公告只证明版本发布，不能证明某刊属于某分区。

来源网站将来可能调整，实际使用时重新核实入口，不把本文件写作年份当作评级年份。不要保存凭证或整站镜像，只保留足够追溯的短片段和必要的用户材料。
