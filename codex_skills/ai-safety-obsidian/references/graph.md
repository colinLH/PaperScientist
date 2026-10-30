# 增量图谱与恢复

1. 若网站已启用且存在 pending，先读 publishing.md 处理已有发布，不创建重复版本。
2. 用唯一运行 ID 生成 plan，读取 needs_extraction 和 errors：

```text
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> obsidian plan --output <WORKSPACE>/work/sync/plan-RUN_ID.json
```

只有完整正文和标题变化才需要提取；自动生成链接区不参与内容哈希。
草稿、重复 ID、来源缺失、手改生成区和 Canvas 会报告错误。先解决这些问题，保留原文件和旧图，不把缺失当删除、不用 baseline 掩盖修订。
如果 needs_extraction 为空、errors 为空、needs_finalize/needs_export 都为 false，且没有待发布，就安静结束。
无须重新提取但 needs_finalize 为 true 时，执行本次 plan 的 finalize、validate、export；仅 needs_export 为 true 时直接恢复 graph export。

3. 读取当前 generation 的 atlas.json，复用已有 canonical ID。对每个变化的来源**完整阅读** fetch_file 指向的 JSON 正文，再创建 extraction JSON：

```json
{
  "source_id": "COPY_FROM_PLAN",
  "content_hash": "COPY_FROM_PLAN",
  "complete": true,
  "nodes": [
    {"id": "p1", "label": "论文简称", "kind": "paper", "category": "attack",
     "full_title": "已核实完整题名", "identity": {"arxiv": "2501.12345"},
     "paper_url": "https://arxiv.org/abs/2501.12345v2", "summary": "有据概括", "limitation": "证据边界"},
    {"id": "m1", "label": "方法", "kind": "method", "category": "attack"}
  ],
  "edges": [
    {"source": "p1", "target": "m1", "relation": "implements", "label": "采用方法",
     "confidence": "EXTRACTED", "confidence_score": 1, "basis": "文章明确事实",
     "evidence": "对应证据的准确转述", "evidence_url": "https://arxiv.org/abs/2501.12345v2",
     "source_location": "日报的相关章节；原论文 §3 / 物理 PDF 第4页"}
  ]
}
```

上述是结构示例，不能作为真实研究证据。source_id/content_hash 必须逐项复制本次 plan 的值。
kind 限 paper/domain/concept/method/benchmark/source。category 使用已有键或简洁英文键。
paper 的 verified_title_aliases 必须是已确认的完整题名变体；aliases 只用于显示和笔记链接。
需要报告链接时添加 kind=source 的报告节点，与其讨论的实体建立有证据的 references 关系。
实体和同名基准不盲目合并；历史实体升级为论文时，用 identity.same_as 指向已有 ID，并写出 identity.reason 的来源依据。
每条边保留原文 HTTP 链接、证据和位置；source/target 可用局部 ID 或已有 canonical ID。
事实用 EXTRACTED/1；分类、跨文联系和待验证建议用 INFERRED，并写清 basis。不要把推断标成作者明确结论。
修订提取该来源当前**完整关系集合**，不能只提差异；旧来源版本保留，其他来源仍支持的关系保留。

4. batch JSON 为数组，每项 `fetch_file` 和 `extraction_file` 是绝对路径。然后执行：

```text
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> graph apply --batch <BATCH_JSON>
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> obsidian finalize --plan <PLAN_JSON>
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> obsidian validate
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> graph export
```

apply 在独立 generation 创建 LadybugDB，关闭重开核验后切换指针。失败的 generation 不替代旧数据库。
finalize 刷新 Markdown、出处、Canvas、累计索引和数据库镜像，核验通过后才确认来源版本。
最后一次 graph export 将最新 Obsidian 链接一并收入下载包。未配置网站时不产生待发布记录。
图谱生成使用 Graphify/GraphML 的聚合视图；完整关系类型和所有出处以 atlas.json 与 LadybugDB 为准。

## 恢复规则

- apply 失败：保留旧 generation、plan 和 extraction，修正具体原因后重试。
- apply 成功而 finalize/validate 失败：图数据库可能已更新，Obsidian 尚未同步完成。保留本次 plan；解决冲突后重跑 finalize、validate、export。账本未确认的来源仍会出现在下一轮 plan；相同 hash 的 apply 幂等。
- finalize 成功但 export 失败：直接恢复 graph export，不重做提取。每次启动检查系统/last-export.json、sync-ledger.json 和当前 generation，以及下载包是否对应当前版本。
- 自动生成区或 Canvas 人工修改：保留现场，让用户选择合并或保留；不能删账本、改哈希或清基线假装成功。个人笔记写在生成标记之外。
- 不修改原报告的 source_id，不删除旧历史，不声称整个跨文件流程是单次原子事务。

总览只放论文与领域，跨论文关系逐行展开，单篇关系左右展开；完整图不堆叠所有边标签。
validate 检查内部链接、附件、Canvas 端点和卡片重叠；此外实际打开或渲染有代表性的 Canvas 检查阅读效果，不能把零重叠当作视觉验收全部通过。
