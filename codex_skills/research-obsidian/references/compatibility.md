# 旧名称与既有数据

主 skill 已从 `ai-safety-obsidian` 改名为 `research-obsidian`。新建实例必须明确提供用户领域，不会默认采用旧领域。
原 README 地址保留升级指引；旧安装包下载地址提供同一个新版包，其顶层目录是 `research-obsidian`。

旧的 schema:1 配置明确属于旧版 AI 安全实例。新版读取时在内存补全其既有领域，并保留原 vault、prefix、workspace、数据库名称、下载路径、source_id、内容哈希和历史。
兼容旧环境变量 AI_SAFETY_OBSIDIAN_CONFIG；新环境变量为 RESEARCH_OBSIDIAN_CONFIG，新变量优先。
新实例使用 `research.lbug`、`research-graph.zip` 和 RESEARCH 生成区标记；旧实例继续使用旧名称和标记，避免破坏已有链接。

已有任务仅需在用户要求升级任务时，将调用名改为 `$research-obsidian`，继续携带原配置绝对路径。保持任务 ID、时刻、模型和通知偏好，并通过真实自动化工具更新。
不把旧配置的 schema 手工改成2来改换领域，不移动或重命名旧论文。新的其他领域应单独 init。

仓库保留旧名称的薄转发入口，其运行要求旁边安装完整的 research-obsidian。新版安装包自身只包含主 skill；旧版使用者应先安装主 skill，再按需要更新定时提示词。
仅更新 skill 不会自动修改已有定时任务、旧配置或历史报告。
