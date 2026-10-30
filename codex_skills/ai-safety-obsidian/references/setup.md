# 首次设置与运行配置

需要本机文件访问、联网论文检索、PDF 读取和页面渲染能力；仅配置日程时不需要实际检索。
图谱依赖 Python 3.12–3.14、LadybugDB、Graphify、NetworkX 和 PyYAML，直接依赖固定在 scripts/requirements.txt。
macOS/Linux 使用 `.venv/bin/python`，Windows 使用 `.venv/Scripts/python.exe`。Windows 没有相应原生 wheel 时可用 WSL，并使用 WSL 内可访问的路径；不得声称未测试的平台已经通过。

先从用户提供的路径或已有配置确定 vault。唯一必须取得的是用户自己的 Obsidian 仓库位置；无法确定时只询问此项。
独立运行目录建议放在仓库外的用户应用数据目录；允许用户指定。默认专区 `AI安全`，每天两篇，09:00 收集、13:00 同步，时区用当前用户时区，不能沿用作者时区。
选择空专区避免碰撞已有同名资料；不自动迁移旧数据库。已存在配置直接复用。

以实际路径替换以下参数：

```text
python3.12 -m venv "<WORKSPACE>/.venv"
"<WORKSPACE>/.venv/bin/python" -m pip install -r "<SKILL>/scripts/requirements.txt"
"<WORKSPACE>/.venv/bin/python" "<SKILL>/scripts/workflow.py" --config "<WORKSPACE>/config.json" init --vault "<VAULT>" --workspace "<WORKSPACE>" --timezone "<USER_TIMEZONE>"
"<WORKSPACE>/.venv/bin/python" "<SKILL>/scripts/workflow.py" --config "<WORKSPACE>/config.json" doctor
```

Windows 可用 `py -3.12 -m venv`，并替换解释器路径。已有受控 Python 环境可复用，但 doctor 会核对直接依赖版本。
需要截图工具时优先使用宿主现有 PDF 渲染能力，或可用的 `pdftoppm`；缺少时安装适合当前平台的 PDF 渲染工具。必须能实际读取和渲染原文，不能用只有摘要的结果补全报告。

`init` 是可重复的，不覆盖现有配置差异，不登记日程，也不下载论文。
它创建空累计索引、附件目录、使用说明、图谱运行目录和可选网站的本地入口。
运行配置位于 skill 之外，升级或分享 skill 不带走用户数据。配置结构：

```json
{
  "schema": 1,
  "vault_root": "/absolute/path/to/vault",
  "workspace": "/absolute/path/to/runtime",
  "prefix": "AI安全",
  "timezone": "Asia/Shanghai",
  "papers_per_day": 2,
  "collect_at": "09:00",
  "sync_at": "13:00",
  "site": {"enabled": false}
}
```

配置不含密钥。改变 vault / prefix / workspace 需要显式迁移数据；单独修改字符串不等于迁移。
init 的时间默认值只用于首次建议，实际日程由 Codex automation 工具登记。
