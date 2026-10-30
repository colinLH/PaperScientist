# 用户指定领域的论文日报与 Obsidian 知识图谱

Skill 名称：`research-obsidian`。研究领域由使用者指定，例如凝聚态物理、肿瘤免疫、教育学或经济学；这些是示例，不是内置范围限制。

将安装包解压后的 `research-obsidian` 文件夹复制到 `$CODEX_HOME/skills/`，未设置 CODEX_HOME 时用 `~/.codex/skills/`。
`.skill` 文件是 ZIP 包。重新打开 Codex 聊天，确认可找到 `$research-obsidian`。

首次在 Codex 中发送：

> 使用 $research-obsidian。研究领域是「你要研究的领域」，关注「关键词或子方向」，排除「不需要的内容」。我的 Obsidian 仓库是「绝对路径」，时区 Asia/Shanghai。请初始化，并创建每天09:00收集2篇论文、13:00同步知识图谱的定时任务。只使用本地 Obsidian。

领域与仓库是首次必要信息；关键词、排除词、来源偏好、分类和每天数量可以定制。
Codex 会创建专属配置和运行环境，并通过自动化工具实际登记任务。未指定专区名时使用领域名称生成文件夹。

已有定时任务中使用：

> 使用 $research-obsidian 执行 daily。配置文件：「运行目录/config.json 的绝对路径」。按配置的领域和筛选条件研究。这是定时执行轮次，不创建或修改定时任务。无变化安静结束，有新增、修订或失败时报告实际结果。

`collect` 只归档论文；`sync` 只同步图谱；`daily` 先归档再同步。`setup` 初始化，`schedule` 创建或调整日程。
同一个 Obsidian vault 可以同时保存多个研究领域，但每个领域使用独立配置、运行目录和专区，避免互相覆盖。不要通过改已有配置的领域名来混用旧数据库。

论文报告覆盖研究问题、背景、贡献、方法/理论、适用的实验或论证、局限和原文证据；不强制非实验论文提供模型基准或消融。适用图表从原文 PDF 截取，已有笔记和来源历史保留。

要求：Codex 可访问本机文件与网络，Python 3.12–3.14，可读取与渲染 PDF；创建日程需要 Codex 自动化工具。图数据库使用 LadybugDB，图谱视图使用 Graphify 与 Obsidian Canvas。网站同步默认关闭，启用时需要自己的 Sites 项目。

旧名称 `ai-safety-obsidian` 与旧配置的处理见 [兼容说明](references/compatibility.md)。新包不含个人配置、研究数据或账号信息。
软件测试使用临时合成材料，不代表真实论文研究、科学结论复现或实际定时触发验证。
