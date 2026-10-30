# 可分享的 Codex Skills

这里的 skill 用于 Codex，不需要启动 PaperScientist Web 服务。

| Skill | 安装包 | 说明 |
|---|---|---|
| `ai-safety-obsidian` | [下载 .skill 包](packages/ai-safety-obsidian.skill) · [SHA-256](packages/ai-safety-obsidian.skill.sha256) | [安装与定时任务用法](ai-safety-obsidian/README.md) |

安装包是 ZIP 格式。将解压后的同名文件夹放入 `$CODEX_HOME/skills/`（默认 `~/.codex/skills/`），在新聊天中调用 `$ai-safety-obsidian`。
首次指定自己的 Obsidian 仓库和时区；skill 会引导初始化环境并通过 Codex 自动化工具登记任务。

维护者重新打包：

```bash
python scripts/package_ai_safety_skill.py
```

打包采用显式文件清单，不收录用户配置、虚拟环境、论文、图谱数据库或账号信息。
