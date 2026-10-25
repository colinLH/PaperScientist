# PaperScientist

一个以自然语言意图驱动的个人科研 Agent。Python 实现，LangGraph 承载通用工具调用循环，LangChain 绑定工具，FastAPI + Gradio 提供 Web 工作区。

用户可以从研究兴趣开始，通过多轮交流完善画像、比较候选方向，再按需要推进文献调研、创新构思、方法实现、实验评估、图表和 LaTeX 写作。LLM 决定下一步行动；没有固定的科研阶段路由。

## 启动

建议 Python 3.11+，使用独立虚拟环境：

```powershell
conda activate llm
python -m pip install -r requirements.txt
# 首次配置时创建 .env；已有 .env 请编辑，避免覆盖。
Copy-Item .env.example .env
python -m uvicorn web.app:app --host 127.0.0.1 --port 8888
```

打开 [Web 工作区](http://127.0.0.1:8888)。也可以运行 `setup_and_run.bat`。

持续任务在后台运行，刷新或切换会话后仍可继续；服务重启会恢复 SQLite 检查点。模型提出关键问题时，页面支持选择选项或自由输入，再恢复同一个 LangGraph 任务。存储位置、迁移、恢复边界与验证方法见 [持久化与中途问答](docs/durable-research-runs.md)。

左侧以项目组织多个聊天，并提供最近对话与搜索。点击项目下的「新聊天」开始独立的多轮会话；首问会被模型总结成简短标题。同项目共享项目记忆和论文库。输入框左下角「＋」添加论文、数据或代码，右下角选择模型，「⚙」设置临时密钥和本地执行权限。

在 `.env` 中设置：

```dotenv
PS_MODEL=deepseek:deepseek-chat
DEEPSEEK_API_KEY=你的密钥
PS_ALLOW_EXECUTION=false
```

也支持进程环境变量，或在 Web 中填写仅用于当前调用的临时 API Key。密钥不写入聊天数据库。无模型配置时进入明确标注的 `demo` 离线演示模式。

本机已验证的解释器为 `D:/anaconda3/envs/llm/python.exe`。不要使用混装 LangChain 0.x 与 core 1.x 的环境。

## 可以怎样使用

- “我对长时程 agent 的记忆感兴趣，先帮我比较两个 CPU 上可验证的研究方向。”
- “选第二个方向。把创新主张拆成可证伪假设，给出每个实验要回答的问题。”
- “实现方法与基线，跑三个 seed，保留原始结果和运行日志，再画误差棒图。”
- “让 reviewer 独立审查这些结果，然后把有证据支撑的部分整理成 LaTeX 草稿。”

运行生成代码前，勾选 Web 中“允许运行工作区 Python / LaTeX”。这是在本机执行可信研究代码，**不是隔离沙箱**。默认只监听回环地址；此版本面向单人本地使用，没有多人服务的鉴权隔离。部署到公网前需要单独加入认证与容器隔离。

## 已实现的能力

| 能力 | 实现 |
|---|---|
| 动态交互 | 通用 decide → tools → decide 循环，多轮会话、SSE 流式输出、停止与恢复、明确的单轮预算 |
| 研究状态 | 用户明确确认方向；计划、任务状态、贡献与评估问题；论文和产物按项目管理 |
| Memory | user_profile、project_memory、topics、session_memory、automation_memory；版本与证据来源；本地 experience recall；离线历史提炼 |
| 上下文 | 原始历史持续累积；micro compact 清理模型视图；sync summary 保存摘要与恢复信息；按需读回历史和完整工具结果 |
| 子代理 | 六类角色，独立上下文和目录，限额调度、等待、消息、取消、恢复和产物导入 |
| 工具 | LangChain 绑定；OpenAlex/arXiv/Crossref、网页检索与读取、PDF、文件、Python、实验记录、matplotlib、LaTeX |
| Skills | 11 个原生技能；视频推荐的 9 个来源共 382 个技能包；带来源前缀、中文/英文检索、分页、按需加载与脚本暂存 |
| MCP | 配置化 stdio / Streamable HTTP，保留嵌套 JSON Schema，工具命名空间与可选允许列表 |
| 可复现产物 | 执行与文件 hash；原文证据记录与贡献审计；图表统计说明；PNG/PDF/SVG/.drawio；多文件 LaTeX 与 ZIP |
| Web | 深色项目侧栏、多会话切换与搜索、首问标题、项目记忆卡片、输入栏模型选择与附件、论文库、子代理、图表和技能检索 |

来源适配、触发边界和实现限制见 [架构文档](docs/architecture.md)。测试证据见 [验证报告](docs/validation.md)。

## 配置与扩展

配置项见 [.env.example](.env.example)。`PS_CONTEXT_TOKENS` / `PS_OUTPUT_TOKENS` 控制上下文与输出预算；`PS_MAX_STEPS` 默认 24，复杂任务达到预算后保留现场并可继续；`PS_MAX_SUBAGENTS` 默认 3。

学术搜索中 arXiv、Crossref 不需要密钥；OpenAlex 可配置 `OPENALEX_API_KEY`。通用网页搜索配置 `TAVILY_API_KEY` 或 `SERPAPI_API_KEY`。服务的配额与网络错误会返回模型，不能据此宣称“没有相关工作”。

把自定义技能放入 `research_skills/<name>/SKILL.md`，或通过 `PS_SKILL_ROOTS` 指定额外根目录（Windows 用分号，Linux 用冒号）。技能头部格式：

```yaml
---
name: my-research-skill
description: Explain when this skill should be used.
---
```

正文是操作指导，可以带 `references/` 或 `scripts/`。脚本不会因为加载技能而自动运行；代码执行仍受设置控制。内置同名技能优先。

视频推荐项目的逐项解析、时间点、来源、借鉴机制和限制见 [视频分析与集成说明](docs/video-skills-analysis.md)。
完整技能目录已经下载到本机 `external_skills/`，独立于项目源代码保存。新环境可恢复相同版本：

```powershell
python scripts/install_research_skills.py
python scripts/install_research_skills.py --check
```

版本和包校验值锁定在 `docs/video-skills.lock.json`；安装后重启服务即可加载。
例如 `nature:nature-reviewer` 与 `scholar:nature-writing` 保留各自来源，避免同名覆盖。
`list_skills` 检索元数据；`load_skill` / `list_skill_resources` 读取正文与资源；
`stage_skill` 只复制到会话目录。共享上游资源通过 `@source/` 读取。
第三方库的全部软件依赖、付费服务和专用 MCP 并未自动安装；当前原生工具和执行设置决定可执行范围。
外部下载保留原许可，未纳入 Git 源码目录：Academic Research Skills 为 CC BY-NC 4.0，
agent-research-skills 未声明许可证，SciPlot 使用自定义 MIT 风格文本。分发或商用时应分别处理。

复制 [mcp.example.json](mcp.example.json) 到 `.paperscientist/mcp.json` 后按实际服务修改并启用。MCP 服务属于可信本地配置；不要加入未知服务或把凭据写入提交。

LaTeX 源文件可直接下载。自动编译需要 PATH 中可用的 Tectonic 或 pdfLaTeX（文献处理建议同时安装 BibTeX）。未安装时工具会返回 `unavailable`，不会将源文件生成冒充 PDF 编译成功。中文稿件需要选择支持中文的文档类/字体与相应编译器。

## 数据、恢复与迁移

默认状态位于 `.paperscientist/research.db`，会话文件位于 `.paperscientist/workspaces/<session_id>/`。不要只备份数据库而遗漏文件。原始消息是追加式存储；压缩只影响模型上下文。Web 可恢复历史会话，API 可以导出会话快照。

旧版入口的实现保存在 `legacy/`，[旧版界面截图](1.png) 保留供对照。原始文档资料与 RL 学习目录保留在本地。新版运行不依赖 MySQL。旧 JSON 对话可显式导入：

```powershell
python -m paperscientist.migrate                 # 仅查看
python -m paperscientist.migrate --apply         # 幂等导入，不删除原文件
python -m paperscientist.refine SESSION_ID       # 用配置的 LLM 提议画像/项目记忆
python -m paperscientist.refine SESSION_ID --apply
```

离线提炼只接受真实用户消息中的原文证据，默认不写入；它不是后台定时服务。旧 MySQL 论文库未自动迁移，避免变更既有数据。

## 开发与测试

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
# 前端交互、动画和音频检查（需要 Node.js）
node --test tests/frontend_effects.test.cjs tests/intro_motion.test.mjs tests/intro_audio.test.mjs tests/intro_hands.test.mjs
# 显式设置 DEEPSEEK_API_KEY 后执行真实模型验证（会调用付费 API）
python scripts/validate_live.py
# 接着恢复同一个验证会话，检查最终交付
python scripts/resume_live_validation.py
```

真实模型验证使用明确标注的合成实验，只验证软件链路。详细结果、首次失败与修复都保存在本地 `.test-output/deepseek-live/`。科研新颖性、真实数据性能与投稿质量仍须针对具体课题独立验证。

API 文档：启动后访问 `/docs`。主要接口为 `/api/chat/{sid}`（SSE）、`/api/sessions`、`/api/sessions/{sid}`、`/api/sessions/{sid}/upload`、`/api/artifacts/{id}`、`/api/sessions/{sid}/export`。

对话页现使用可重连的持久化事件流 `/api/sessions/{sid}/events`，支持按类别折叠工具、文件预览、逐轮差异与撤销、轮次导航。实现和历史版本限制见 [对话时间线说明](docs/conversation-timeline.md)。

文件在右侧分栏预览，对话与输入框保留在左侧；拖动分隔线调整宽度，PDF 支持翻页，关闭预览后恢复完整对话布局。开场声音默认开启，浏览器阻止自动播放时在首次点击或按键后接续播放。

网页保留动态视觉效果，并对滚动、流式增量渲染和服务内存进行了优化。实测数据、复现方法及本地模型启动选项见 [Web 性能验证](docs/ui-performance.md)。

首页新增可正反向滚动的六幕景深开场与渐变配乐，Start 进入工作台；可用 `/?workspace=1` 直接进入。音乐来源、低开销策略、发送／停止按钮及进展展示说明见 [开场与交互验证](docs/cinematic-entrance.md)。

科研环节可由主代理动态委派给文献、构思、设计实现、实验和写作专家，各自使用独立的工具与技能范围；专家可继续并行调用检索或通用叶子任务。角色提示词、权限和检查可由操作者扩展，见 [专家代理与 harness](docs/agent_capabilities.md)。

完整初稿会进入章节论证、实验覆盖、学术润色和 `anti-defensive-writing` 的优化流程。绘图优先使用 Top-Conf Figure Gallery 参考检索与本地可重现矢量绘图适配器，见 [论文质量与绘图](docs/research-quality-upgrade.md)。单/双栏、页面、图表宽度和有效字号由 [版式契约与 PDF 检查](docs/manuscript-layout.md) 约束；源码编译成功不等于版式合格。

相关课题先评估公共 benchmark 的适用性，再固定版本、数据、划分、指标和预算，登记协议并执行带收据的评测。入口与真实结果格式见 [benchmark-evaluation](research_skills/benchmark-evaluation/SKILL.md)。本地合成 smoke、选定子集和官方完整基准成绩严格区分。

提交、推送和每日开发记录遵循 [交付记录规则](docs/development-delivery.md)。
