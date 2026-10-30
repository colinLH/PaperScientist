# 安装与使用

将整个 `ai-safety-obsidian` 文件夹复制到 `$CODEX_HOME/skills/`，未设置 CODEX_HOME 时用 `~/.codex/skills/`。
`.skill` 文件是 ZIP 包：解压后保留同名顶层目录。重新打开 Codex 聊天，确认可找到 `$ai-safety-obsidian`。

首次在 Codex 中发送（换成自己的仓库路径）：

> 使用 $ai-safety-obsidian。我的 Obsidian 仓库是 `/我的仓库绝对路径`，时区 Asia/Shanghai。请初始化运行环境，并创建每天09:00收集2篇AI安全论文、13:00同步知识图谱的定时任务。只使用本地 Obsidian。

Codex 会准备 Python 运行环境，保存专属配置，并通过自动化工具实际登记两项任务。
如想创建单一日程，可要求“每天09:00执行 daily，先归档再同步”。
首次路径确认完成后，后续任务只需携带同一配置路径。

在已有定时任务的提示词中写：

> 使用 $ai-safety-obsidian 执行 daily。配置文件：`/我的运行目录/config.json`。这是定时执行轮次，不创建或修改定时任务。无变化安静结束；有新增、修订或失败时报告实际结果。

需要分开执行时将 daily 改为 collect 或 sync。需要立即试跑时在聊天中说“使用该配置执行 daily”。

要求：Codex 可访问本机文件和网络，Python 3.12–3.14，可读取与渲染 PDF；创建日程需要当前环境有 Codex 自动化工具。图谱数据库使用 LadybugDB，图谱视图使用 Graphify 与 Obsidian Canvas。平台原生依赖以实际安装检查为准。

网站同步为可选能力，默认关闭，需要使用者自己的 Sites 项目及可用插件。安装包不含论文、数据库、个人路径、账号或凭据。
本包复用并移植原有日报/图谱工作流；测试使用临时合成材料，只验证软件行为，不代表已阅读或复现真实论文。
