# 论文日报

以下 `<PYTHON> / <SKILL> / <CONFIG>` 均指 setup 确定的绝对路径。日期按配置 timezone 计算。

1. 读取 `<VAULT>/<PREFIX>/系统/collection-index.json` 和 `01-报告` 的现有正文，含当天草稿。按规范 DOI、PMID、arXiv、完整题名、已核实的完整题名别名查重。会议版、预印本和版本更新视为同篇，`awaiting_graph` 也已经归档。
2. 每天目标为配置的 papers_per_day，扣除当天已登记的论文；恢复当天草稿后只补不足数量。当天重跑不再新增一整批。没有足量可靠资料就报告实际数量，不编造、不拿旧论文凑数。
3. 按 domain.name、keywords、exclude_keywords 与 sources 确定检索范围。组合学科术语、同义词与常用语言，阅读候选摘要后判断研究问题是否符合范围，不能只靠命中一个词。来源偏好未指定时，根据学科选择一手期刊/学会会议/机构仓库/合法预印本；例如生物医学可用 PubMed 定位再读原刊全文，物理数学可查学科期刊及 arXiv，人文社科可查出版机构和学科数据库。这些是选源示例，不是固定名单。核对题名、真实发表日期、发表类型与固定阅读版本，预印本和同行评审论文明确区分。全文不可取得就报告未完成或选择其他候选，不绕过访问限制、不把摘要扩写当全文。
4. 固定 PDF 存入 `<PREFIX>/附件/PDF`。与论文实际内容相关的框架、方法、数据、结果或论证图表从原文 PDF 渲染或截图，存入 `<PREFIX>/附件/图表/YYYY-MM-DD`。在相应段落嵌图，保留完整坐标轴和图例；记录论文题名、原图编号、物理 PDF 页码、原文链接和中文解释。不得生成图冒充原图。

创建或恢复当天同一 source_id：

```text
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> obsidian new-report --date YYYY-MM-DD --title "<USER_DOMAIN>论文日报：本次论文题名"
```

命令返回真实文件路径和 UUID。保留 YAML 中的 source_id 和 reading_date；未完成时 complete:false。
每篇论文包含：完整题名/版本/日期/出处、摘要、研究背景、问题与动机、贡献、方法或理论论证、证据与结论、假设与局限、与既有研究的联系和来源。
按研究类型细化证据：实证研究记录样本、条件、指标、单位、统计与对照；算法研究记录模型/数据/预算/基准和适用消融；理论论文记录定义、假设、定理、证明思路与适用范围；定性/人文研究记录材料、分析方法、论证链与解释边界；综述记录检索覆盖和纳入标准。
不适用的实验、消融、统计显著性或模型排名明确标为不适用，不虚构内容。区分作者结果、整理者分析、未复现实验或未独立复核证明。原文没有适用图表时如实说明，不强制凑图。
本地图片采用相对路径，例如 `![](../附件/图表/YYYY-MM-DD/figure-1.png)`。

完整阅读、核验本地 PDF 和所有嵌图后才设 `complete:true`。再创建候选索引 JSON 数组：

```json
[
  {
    "title": "Verified full paper title",
    "doi": "10.9999/example",
    "read_version": "Publisher version, verified publication date",
    "source_url": "https://example.org/verified-paper",
    "collected_on": "2026-10-30",
    "pdf_local": "<PREFIX>/附件/PDF/fixed-version.pdf",
    "report_file": "<PREFIX>/01-报告/<new-report 返回的实际文件名>"
  }
]
```

上面是字段示例，不是推荐论文。ID、日期和路径必须替换为实际值；没有 DOI、PMID 或 arXiv 就省略，完整题名仍可用于去重，不能为了填写字段而猜编号。`pmid` 为已核实的 PubMed ID；arxiv_id 支持新式与旧式编号并规范化版本号。
`verified_title_aliases` 只收录已核实同一论文的完整题名变体，简称不作为去重身份。
pdf_local 和 report_file 相对 vault 根，不是相对运行目录。

```text
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> obsidian register --file <CANDIDATES_JSON>
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> obsidian validate
```

完全相同的登记可重放；新记录与既有身份冲突则拒绝。修订编辑原报告，保留 ID，不通过新增登记制造重复。
登记脚本检查结构、文件和身份，不证明论文内容正确；原文阅读与图表核验仍是 Codex 的工作。
日报完成不等于已更新图谱；独立 collect 等待 sync，daily 则继续同步。
