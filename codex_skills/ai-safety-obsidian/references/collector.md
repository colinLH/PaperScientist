# 论文日报

以下 `<PYTHON> / <SKILL> / <CONFIG>` 均指 setup 确定的绝对路径。日期按配置 timezone 计算。

1. 读取 `<VAULT>/<PREFIX>/系统/collection-index.json` 和 `01-报告` 的现有正文，含当天草稿。按规范 arXiv、DOI、完整题名、已核实的完整题名别名查重。会议版、预印本和版本更新视为同篇，`awaiting_graph` 也已经归档。
2. 每天目标为配置的 papers_per_day，扣除当天已登记的论文；恢复当天草稿后只补不足数量。当天重跑不再新增一整批。没有足量可靠资料就报告实际数量，不编造、不拿旧论文凑数。
3. 从 AI 顶会、安全顶会、arXiv 等原始来源检索。优先新近且与 AI 安全相关的工作，核对真实发表日期、会议身份、完整题名和阅读版本。阅读完整原文及相关附录，不把摘要扩写当全文分析。
4. 固定 PDF 存入 `<PREFIX>/附件/PDF`。必要的框架、方法、结果、消融图从原文 PDF 渲染或截图，存入 `<PREFIX>/附件/图表/YYYY-MM-DD`。在相应段落嵌图，保留完整坐标轴和图例；记录论文题名、原图编号、物理 PDF 页码、原文链接和中文解释。不得生成图冒充原图。

创建或恢复当天同一 source_id：

```text
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> obsidian new-report --date YYYY-MM-DD --title "AI 安全论文日报：论文 A 与论文 B"
```

命令返回真实文件路径和 UUID。保留 YAML 中的 source_id 和 reading_date；未完成时 complete:false。
每篇论文包含：完整题名/版本/日期/出处、摘要、背景、动机与挑战、解决措施与贡献、设计框架与创新细节、各实验维度与消融、结果及局限、与既有研究的联系和来源。
报告实验数字时带单位、指标方向、分母、模型/数据/权限/预算及比较条件；区分作者结果、整理者分析、未复现实验，不虚构统计显著性或跨基准排名。
本地图片采用相对路径，例如 `![](../附件/图表/YYYY-MM-DD/figure-1.png)`。

完整阅读、核验本地 PDF 和所有嵌图后才设 `complete:true`。再创建候选索引 JSON 数组：

```json
[
  {
    "title": "Verified full paper title",
    "arxiv_id": "2501.12345",
    "read_version": "arXiv:2501.12345v2",
    "source_url": "https://arxiv.org/abs/2501.12345v2",
    "collected_on": "2026-10-30",
    "pdf_local": "AI安全/附件/PDF/2501.12345v2.pdf",
    "report_file": "AI安全/01-报告/2026-10-30｜AI安全论文日报.md"
  }
]
```

上面是字段示例，不是推荐论文。ID、日期和路径必须替换为实际值；没有 arXiv 或 DOI 就省略，不能猜。
`verified_title_aliases` 只收录已核实同一论文的完整题名变体，简称不作为去重身份。
pdf_local 和 report_file 相对 vault 根，不是相对运行目录。

```text
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> obsidian register --file <CANDIDATES_JSON>
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> obsidian validate
```

完全相同的登记可重放；新记录与既有身份冲突则拒绝。修订编辑原报告，保留 ID，不通过新增登记制造重复。
登记脚本检查结构、文件和身份，不证明论文内容正确；原文阅读与图表核验仍是 Codex 的工作。
日报完成不等于已更新图谱；独立 collect 等待 sync，daily 则继续同步。
