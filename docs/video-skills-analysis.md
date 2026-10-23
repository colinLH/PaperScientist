# 视频推荐的科研 Skills：解析与 PaperScientist 集成

验证日期：2026-10-23。视频为用户提供的 `downloads/skills_recommendmp4.mp4`，时长 86.23 秒，592×1280。使用逐段画面检查与本地语音转写交叉核对；专有名词以画面和仓库为准。原始 ASR 有明显同音误识，不能直接拿它当仓库名清单。视频指纹见 [metadata.json](video-evidence/metadata.json)。

## 识别结果

口播明确推荐 **8 个项目**，分为六类。约 10 秒的文档目录另外出现 **Science-Research-Writing-Skills**，一并收录为补充项。下表数量来自本次固定版本的实际 SKILL.md 文件，不沿用视频的宣传数字。

| 视频位置 | 类别与项目 | 下载技能数 | 本地位置 / 调用前缀 | 用途与适配判断 |
|---|---|---:|---|---|
| 约 14–26 秒 | [Orchestra-Research/AI-Research-SKILLs](https://github.com/Orchestra-Research/AI-Research-SKILLs) | 98 | external_skills/orchestra / orchestra: | ML 训练、评测、工程实现与科研编排。借鉴实验迭代与阶段性综合分析的双循环；保留用户意图和预算约束。 |
| 同一段 | [Galaxy-Dawn/claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) | 45 | external_skills/scholar / scholar: | 从构思、编程、结果分析到写作与返修。引用核验、项目文件规划、结果分析适合复用；Claude 的 hooks/commands 不自动装入本项目。 |
| 约 26–36 秒 | [Imbad0202/academic-research-skills](https://github.com/Imbad0202/academic-research-skills) | 5 | external_skills/academic / academic: | 深度研究、论文写作、审稿、整合编排和研究筛选。借鉴证据覆盖与检查边界；原始十阶段 pipeline 仅供参考，不成为我们固定路由。 |
| 约 37–46 秒 | [lingzhi227/agent-research-skills](https://github.com/lingzhi227/agent-research-skills) | 31 | external_skills/research / research: | 文献/GitHub 调研、创新评估、数学—代码对应、实验、写作、引用与结果追溯。适合方向探索和方法落地。 |
| 约 47–59 秒 | [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | 177 | external_skills/scientific / scientific: | 生物、化学、材料、统计分析、科学数据库等。完整保留技能资源，按课题检索加载；专用软件、数据库 API 和服务配置仍按需准备。 |
| 约 60–71 秒 | [peterbruce716-art/sciplot-figure-skill](https://github.com/peterbruce716-art/sciplot-figure-skill) | 1 | external_skills/sciplot / sciplot: | 数据到图形映射、图形规范、统计语义与可复现产物。原生 plot_results 融入轻量图表说明与 provenance 检查；没有声称执行其整套 QA。 |
| 同一段 | [Agents365-ai/drawio-skill](https://github.com/Agents365-ai/drawio-skill) | 1 | external_skills/drawio / drawio: | 可编辑架构图、流程图、图形结构与导出。原生 draw_framework 新增 .drawio XML，同时保留 PNG/PDF/SVG/JSON。 |
| 约 72–83 秒 | [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) | 23 | external_skills/nature / nature: | 期刊表达、论文阅读、统计、绘图、模拟审稿和返修。采用来源锚点、独立上下文评审与评审后综合；按用户目标选择风格。 |
| 约 10 秒目录补充 | [YerayL/Science-Research-Writing-Skills](https://github.com/YerayL/Science-Research-Writing-Skills) | 1 | external_skills/writing-coach / writing-coach: | 章节结构、时态、证据强度与措辞校准、草稿改写。作为额外写作参考，未误记为口播单独推荐。 |
| **合计** | **9 个来源** | **382** | **加上 11 个本地技能，共 393 个可检索技能** | |

辨识边界：视频分辨率有限，DrawIO 画面的仓库名可辨，owner 细字不能可靠逐字读取；这里按名称、目录和 README 内容匹配到 Agents365-ai/drawio-skill。补充写作项的 owner 未在画面展示，按完整名称查到上述原仓库。两者的匹配依据已记录在版本清单中，没有把检索匹配当作可见完整 URL。

视频还口头提到 PubMed、ChEMBL，它们是科学数据库，不是额外两个技能仓库。相关访问指导包含在 scientific 的数据库技能和 nature 的检索资源中。原视频中的使用文档没有可辨认的完整 URL，未伪造下载链接。Nature Skills 是社区项目名称，不代表 Nature 官方认证或录用保证。

关键画面：
[文档目录](video-evidence/crop_0010.png) · [自动科研](video-evidence/crop_0020.png) ·
[可信科研](video-evidence/crop_0030.png) · [深度调研](video-evidence/crop_0040.png) ·
[AI for Science](video-evidence/crop_0050.png) · [可视化](video-evidence/crop_0065.png) ·
[Nature Skills](video-evidence/crop_0075.png)。

## 下载和版本管理

- 每个源固定到 40 位 Git commit；所有包保留完整目录，而非只复制 SKILL.md。
- 下载位置为本项目 external_skills，未修改 Codex 全局技能、用户 hooks 或其他 agent 的配置。
- 本次下载 4,585 个文件，约 83.06 MB，包含脚本、参考资料、模板、资源和上游许可。
- Academic 的跨包 shared 目录也已补齐，其他来源保留 README/许可证等。通过 load_skill 的 @source/ 路径访问。
- [video-skills.lock.json](video-skills.lock.json) 保存版本、来源、画面时间、技能路径以及逐包 SHA-256 树校验值。
- 下载目录被 Git 忽略，避免把不同许可的上游代码混入主项目。复现安装器按固定版本下载所需内容，不运行上游安装脚本。
- 两次固定版本校验均通过。安装器遇到本地修改或校验不符会报告错误，不静默覆盖已有包。

恢复与检查：

    python scripts/install_research_skills.py
    python scripts/install_research_skills.py --check

只恢复某个来源可加 --source nature。安装后重启 PaperScientist 服务。--record-hashes 仅用于审查初始版本后记录校验值，日常恢复不需要。

许可按各仓库原文保留：大部分为 MIT，Nature 为 Apache-2.0，Academic 为 CC BY-NC 4.0，research 未声明许可证，SciPlot 的 LICENSE 是自定义 MIT 风格简化文本。下载保存不意味着可以将这些包统一换成主项目许可证发布。

## 已经融合的机制

### 1. 技能发现与渐进加载

原实现只扫描一层目录，重名保留第一个，并把检索结果截断到固定前缀。这对几百个技能不可用。

新实现递归发现技能，以来源前缀区分同名技能，提供中英文查询扩展、排名、来源筛选和分页。系统提示中只放原生技能与来源摘要，不把 382 份正文灌进上下文。选择和执行仍由 LLM 根据意图决定。

工具接口：
- list_skills：查询全目录，返回 total / next_offset。
- load_skill：加载选定技能或引用资源，并返回来源。
- list_skill_resources：列举脚本、参考资料和共享资源。
- stage_skill：将完整包复制到会话工作区并记录 hash，不执行脚本或自动安装依赖。

上游说明作为参考内容包装：其宿主工具名称、固定步骤、自动安装、定时循环、广告、权限变更等不能取代当前系统策略和用户要求。外部资源不会变成新的用户指令。

### 2. 证据记录与科研审计

新增 record_evidence，将 claim_id、原文片段、source_id、来源 hash、位置、支持/反驳/背景关系和解释分开存储。论文片段只对已检索的标题/摘要核对；完整文本需要对应的注册文本产物，不能把摘要读取冒充全文阅读。

新增 audit_research，检查未解析证据、来源改动、结果文件变化、实验 provenance 和评估覆盖。保留矛盾证据与没有测量结果的缺口。报告明确限定于当前会话证据/结果及项目主张，跨会话文件需显式导入。检查通过仅表示结构关系完整，不能证明语义支持、因果、新颖性或统计有效性。

### 3. 有预算的实验—综合分析循环

新增 adaptive-research 原生技能。实验前明确预测、预算、停止条件；实验后区分观测与解释。出现意外或边际收益降低时，综合证据并更新计划，可回到文献、提出转向、写作或停止。

这借鉴 Orchestra 的双循环思想，使用现有计划、日志和实验记录工具。没有新增永久后台循环或固定执行次数，仍遵循用户逐步交互的设计。

### 4. 可核对的独立审稿

新增 independent-review 原生技能与 isolated_review 调度模式。指定源 artifact_ids 后，调度器校验 hash 并复制评审包；禁用项目/画像继承、记忆检索、其他父任务产物读取和任意代码执行。原件后续变化不影响已复制的评审材料。预先定义评审侧重点，评审期间不共享其他人的报告；报告完成后冻结，再做综合与一致性检查。

评审人数由任务与预算决定，不照搬上游固定人数。共享上下文的角色扮演不能描述成独立评审；多个同类 LLM 的一致意见也不是独立科学证据。隔离包、不可变副本和父状态隔离均有新增测试；本次没有额外发起付费多审稿任务。

### 5. 图表说明与可编辑框架图

plot_results 保存 figure_contract.json：科学问题、列映射、数据 hash、sample_size、独立抽样单位、误差棒定义、数据 provenance、输出 hash 和报告缺口。缺少统计定义会留下说明；NaN/Inf 不会静默进入结果图。成功渲染与发表质量分别表示。

draw_framework 从同一图结构生成原生 .drawio，节点、边与文本可编辑；中文、XML 转义和保留 ID 冲突均经过测试。PNG/PDF/SVG 仍由本地 matplotlib 输出，不依赖 draw.io 桌面软件。复杂拓扑的完整自动布局/碰撞检查不在这个轻量适配器范围内。

### 6. 写作与方法对齐

现有 method-design、academic-figures 和 evidence-review 已更新，明确如何调用新增能力及进一步读取上游技能。方法设计增加概念—公式—Python 符号—测试—消融对应关系。Nature/Scholar/写作补充库按需提供章节结构、修稿和证据强度措辞指导，不强制所有论文使用同一个期刊风格。

## 当前可用范围

外部 **技能材料** 已全部下载、索引并可加载；外部项目的 **所有执行环境** 不等于全部部署。

- SciPlot 固定版本明确要求 Python 3.14。当前主项目 Python 3.12 使用原生 matplotlib 工具，借鉴其图表说明机制，未运行不兼容的 SciPlot QA 程序。
- K-Dense 的专业包、付费搜索、云实验室、图像模型等需要对应依赖和凭据；它们不会因目录存在而自动可用。
- Academic 的固定流水线、Claude 专用 hooks，及部分 ~/.claude/... 绝对路径经过提示适配，不能直接当成本项目工具调用。
- Nature 部分资源包含非 Python 工具；保持原样作为上游资料，主项目新增实现全部是 Python。
- 图像视觉审查需要实际查看输出或配置视觉模型；结构检查不会声称已经完成视觉审查。

## 验证

- 固定版本：9 个来源、382 个包与共享资源 hash 全部通过离线校验。
- 自动测试：新增测试覆盖命名空间、中文检索、分页、资源边界、暂存、伪造引用拒绝、来源变更、图表说明、可编辑 XML 和盲审上下文边界。最终结果见下方。
- 新增两个本地技能通过 skill-creator 的结构校验。
- 最终完整测试集 27 项通过；补充的隔离审稿与压缩恢复回归测试也通过。测试日志：.test-output/video-skills/tests.log 和 review-regressions.log。
- 浏览器实测：技能库显示 393 项，中文“框架图”检索返回 DrawIO 等匹配结果；支持读取正文。
- DeepSeek 真实调用报告与生成产物保存在 .test-output/video-skills/live-report.json。两轮均 completed，17 次工具调用，8 项断言全部通过，无工具失败：真实检索与加载 DrawIO/Nature 技能及 reference，生成原生图和 .drawio，登记合成实验、原文证据、统计图说明和科研审计。
- 真实模型审计保持 needs_review，明确指出没有 measured 实验，合成数据不能支持真实科学结论。生成的框架图和统计图已实际查看。
- 初次 live 验证脚本误把 SSE data 当作包含 type 的整条事件，修正为分别解析 event/data 后重新跑通；这是验证客户端解析问题，已保留可复现脚本。

主要代码：
[paperscientist/skills.py](../paperscientist/skills.py)、
[paperscientist/evidence.py](../paperscientist/evidence.py)、
[paperscientist/tools.py](../paperscientist/tools.py)、
[paperscientist/artifacts.py](../paperscientist/artifacts.py)、
[paperscientist/ui.py](../paperscientist/ui.py)。
