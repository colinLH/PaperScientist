# 可分享的 Codex Skills

这里的 skill 用于 Codex，不需要启动 PaperScientist Web 服务。

| Skill | 安装包 | 说明 |
|---|---|---|
| `research-obsidian` | [下载 .skill 包](packages/research-obsidian.skill) · [SHA-256](packages/research-obsidian.skill.sha256) | [用户指定领域、安装与定时任务用法](research-obsidian/README.md) |

安装包是 ZIP 格式。将解压后的 `research-obsidian` 文件夹放入 `$CODEX_HOME/skills/`（默认 `~/.codex/skills/`），在新聊天中调用 `$research-obsidian`。
首次指定自己的研究领域、Obsidian 仓库和时区；可设置关键词、排除词、来源偏好与图谱分类。
不同领域各用独立配置、运行目录和专区，日程通过 Codex 自动化工具登记。

旧的 `ai-safety-obsidian` 名称保留为薄转发入口，旧安装包下载地址也提供新版同一包；详见 [兼容说明](research-obsidian/references/compatibility.md)。

维护者重新打包：

```bash
python scripts/package_research_obsidian_skill.py
```

打包采用显式清单，不收录用户配置、虚拟环境、论文、图谱数据库或账号信息。
