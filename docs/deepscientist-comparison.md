# PaperScientist 与 DeepScientist 的研究工作流对照

这次对照以 DeepScientist 的 `b366244` 和改动前 PaperScientist 的 `1c44ae4` 为起点，逐项查看仓库实现。下文的运行验证来自 PaperScientist 本地。双方没有在同一研究任务和预算下对跑，因此这里比较研究者可以完成的操作，不对论文质量、成功率或费用排名。[DeepScientist 源码](https://github.com/ResearAI/DeepScientist/tree/b36624417f0c6b8238ec02db37b94d6db2faa5b0) · [PaperScientist 比较起点](https://github.com/colinLH/PaperScientist/tree/1c44ae44d2b66453b410df284c461ce60eb0365b)

## 从材料、分叉到实验结论

| 研究者要做的事 | DeepScientist 的实现 | PaperScientist 原有做法与本次改动 |
|---|---|---|
| 接着一篇论文或已有实现研究 | 启动研究时区分已有材料和待复现的基线。[研究入口](https://github.com/ResearAI/DeepScientist/blob/b36624417f0c6b8238ec02db37b94d6db2faa5b0/docs/en/02_START_RESEARCH_GUIDE.md) | 原有上传、论文检索与产物登记分处不同入口。现在会话可以生成一份起始材料清单，固定仓库提交、保存选定源码并逐一核对 Git 对象，同时记录论文 PDF 与已有产物的指纹。清单把待复现的基线明确标出。 |
| 回看为什么换了一条研究路线 | Canvas 从 Git 分支、阶段产物和事件重建研究路径，可追踪代码的演变。[运行时与 Canvas](https://github.com/ResearAI/DeepScientist/blob/b36624417f0c6b8238ec02db37b94d6db2faa5b0/docs/en/06_RUNTIME_AND_CANVAS.md) | 原有会话分叉可以保留历史，但判断依据分散在聊天里。现在项目「研究路线」显示亲缘、分叉理由、结论和下一步，可比较登记过的产物。主 Agent 能读回本项目已停止或被否决路线的结论。 |
| 把一个项目的基线带到另一个项目 | 注册表能发布并挂接基线资源。[基线注册表](https://github.com/ResearAI/DeepScientist/blob/b36624417f0c6b8238ec02db37b94d6db2faa5b0/src/deepscientist/registries/baseline.py) | 以前要在新项目里找回协议和结果。现在由主 Agent 在源会话导出已核验的汇总，在目标会话按 ID 挂接。接收项目可见版本、范围、样本数、指标及证据指纹。比较时保留两次运行的 ID，继承同一份回执的分叉不会出现虚假的零差值。 |
| 关掉页面后观察长实验 | 后台命令服务和 monitor 管理运行过程及日志。[执行服务](https://github.com/ResearAI/DeepScientist/blob/b36624417f0c6b8238ec02db37b94d6db2faa5b0/src/deepscientist/bash_exec/service.py) · [监控实现](https://github.com/ResearAI/DeepScientist/blob/b36624417f0c6b8238ec02db37b94d6db2faa5b0/src/deepscientist/bash_exec/monitor.py) | 原有研究对话可恢复，单次工作区 Python 却有五分钟上限。现在可将输入冻结后交给独立进程，在「产物与图表 → 后台实验」查看输出、错误、退出码和回执。预注册基准也可走这条路径，完成后逐例评分并登记。 |
| 离开网页后继续同一任务 | 提供交互式 TUI、多个编码 CLI 和双向飞书连接器。[TUI](https://github.com/ResearAI/DeepScientist/blob/b36624417f0c6b8238ec02db37b94d6db2faa5b0/docs/en/05_TUI_GUIDE.md) · [运行器](https://github.com/ResearAI/DeepScientist/blob/b36624417f0c6b8238ec02db37b94d6db2faa5b0/src/deepscientist/runners/builtins.py) · [飞书](https://github.com/ResearAI/DeepScientist/blob/b36624417f0c6b8238ec02db37b94d6db2faa5b0/docs/en/18_FEISHU_CONNECTOR_GUIDE.md) | 终端现在直接连接工作台已有的服务和检查点，可以启动、观察、回答问题、停止和继续任务。可选择把单个任务的状态发送给本机配置的飞书机器人。问题正文和实验日志留在工作台。 |

## PaperScientist 在个人研究中的长处

- **精读材料可以留在自己的知识库。** 关键词检索、原文 PDF、原图页截图和中文精读笔记可以一并归档到本地 Obsidian，之后能直接回到原文核对。[精读与归档](keyword-paper-reading.md)
- **从一张结果图可以追到哪些样本真正参与了比较。** 协议固定案例、划分、方法、种子和评分口径。配对分组报告保留计划分母、超时、错误与缺失。新增路线比较沿用这些记录，也可以读取本会话直属评估专家的运行。没有完整独立结果时，页面会说明原因。[基准协议](../research_skills/benchmark-evaluation/protocol.md) · [路线比较实现](../paperscientist/research_routes.py)
- **论文交付保留可复核、可编辑的成果。** 实测结果图依赖工作区数据，机制图有可编辑源文件。盲审专家接受冻结的材料包，最终 PDF 按稿件约定检查栏宽、页数及图文布局。这些能力对反复核图、改图和交付双栏论文尤其有用。[绘图规格](../research_skills/figure-forge/specification.md) · [盲审隔离](../paperscientist/subagents.py) · [稿件布局](../paperscientist/manuscript_layout.py)

DeepScientist 在需要直接合并代码分支、切换 Codex／Claude／Kimi／OpenCode 运行器，或从飞书接收指令的场景中覆盖更广。PaperScientist 的研究路线使用会话快照及实验指纹，终端驱动同一个本地 Agent。飞书订阅只报告状态，当前版本没有把外部聊天消息接成工作区命令。

## 在本地复核

1. 在工作台打开一个项目的「研究路线」，从基线会话分叉，写下想区分的两种解释。子路线先继承基线回执。运行新的匹配评估后，才能看到差值、两侧分母与运行 ID。
2. 要用已有资料开工，可在聊天中给出公开仓库、论文或当前会话的产物 ID，要求固定起点。仓库最多选择 20 个具体文件。如需引用另一项目的已测基线，在源会话的「研究路线 → 跨项目基线」选择已核验运行，点击「生成基线引用」，把引用粘贴到目标会话的同一面板，即可对照。主 Agent 也可以经由研究工具完成相同操作。
3. 要跑长基准，启用该任务的本地执行权限。把适配器依赖列入预注册协议的 `input_paths`，指定 `run_benchmark` 的 `background_name`。超过五分钟的预算自动转入后台，最多 24 小时。用同一名称轮询原任务，完成后用 `audit_benchmarks` 查看结果、覆盖率与失败记录。
4. 终端示例见[项目首页](../README.md#从现有研究继续)。终端与网页共享同一会话和任务 ID。

本次本地验收覆盖真实 Git 提交与源码校验、独立 Python 子进程跨 Web 服务重启、后台预注册基准的自动登记、已继承回执的去重、输入及回执篡改后的拒绝比较、普通评估专家和盲审专家的可见范围，以及桌面与手机宽度的工作台。实验数据来自合成的适配器验证任务。研究终端通过真实本地 HTTP 和离线演示模型完成了启动与状态回读。机器人订阅使用模拟服务验证签名、去重与不确定投递。
