# 首次设置与运行配置

需要本机文件访问、联网论文检索、PDF 读取与页面渲染能力。图谱直接依赖固定在 scripts/requirements.txt，使用 Python 3.12–3.14。
macOS/Linux 解释器为 `.venv/bin/python`，Windows 为 `.venv/Scripts/python.exe`。原生依赖不可用时可用 WSL，路径也要使用 WSL 内的路径。未测试的平台不能宣称已验证。

从用户请求或现有配置确定两项必要信息：**研究领域**和 **Obsidian 仓库位置**。缺失时一次询问缺失项，不默认选择任何领域。
将用户描述保存为 domain.name；关键词、跨语言同义词、排除词和偏好的期刊/会议/数据库保存为对应数组。未提供可留空，由研究领域指导检索，不自动填入其他领域的会议名单。
分类可稍后按实际论文确定；不要套用固定学科分类。

独立运行目录放在 vault 外。默认每天两篇、09:00收集、13:00同步，时区用当前用户时区。
`--prefix` 未指定时，从领域名称生成安全目录名。每个领域需要独立配置、运行目录、专区；用户可以主动指定包含多个学科的交叉领域名称，作为一个明确的研究范围。

使用实际绝对路径替换以下参数：

```text
python3.12 -m venv "<WORKSPACE>/.venv"
"<PYTHON>" -m pip install -r "<SKILL>/scripts/requirements.txt"
"<PYTHON>" "<SKILL>/scripts/workflow.py" --config "<WORKSPACE>/config.json" init --vault "<VAULT>" --workspace "<WORKSPACE>" --domain "<USER_DOMAIN>" --timezone "<USER_TIMEZONE>"
"<PYTHON>" "<SKILL>/scripts/workflow.py" --config "<WORKSPACE>/config.json" doctor
```

可选参数：`--prefix`、`--papers-per-day`、`--collect-at`、`--sync-at`；`--keyword`、`--exclude-keyword`、`--source` 可重复提供。
Windows 可用 `py -3.12 -m venv` 创建环境。截图优先使用宿主已有 PDF 工具或 pdftoppm；缺少时安装适合平台的渲染工具。无法读取原文时不得补写全文报告。

下面使用凝聚态物理演示结构，所有领域内容都应替换为用户实际范围：

```json
{
  "schema": 2,
  "domain": {
    "name": "凝聚态物理",
    "keywords": ["二维材料", "two-dimensional materials"],
    "exclude_keywords": ["纯器件制造工艺"],
    "sources": [],
    "categories": {
      "materials": {"name": "材料体系", "color": "#65c8ad"},
      "theory": {"name": "理论机制", "color": "#b2a3f7"}
    }
  },
  "vault_root": "/absolute/path/to/vault",
  "workspace": "/absolute/path/to/runtime",
  "prefix": "凝聚态物理",
  "timezone": "Asia/Shanghai",
  "papers_per_day": 2,
  "collect_at": "09:00",
  "sync_at": "13:00",
  "site": {"enabled": false}
}
```

`domain.sources` 是检索偏好，允许权威来源名称或网址；除非用户明确要求只查这些来源，否则不要当作排他白名单。
`domain.categories` 键使用稳定小写英文 ID，name 是面向用户的显示名，color 可省略。没有预设分类时，从当前领域论文中归纳；只有通用后备分类，不注入示例分类。

init 创建空索引、目录、使用说明和实例归属文件，不下载论文、不登记日程。它可重复执行，但不覆盖已有不同配置。
配置与实例归属文件位于 skill 之外，升级不携带用户资料。修改 keywords/exclude_keywords/sources 会影响未来收集，不删除旧资料；修改 categories 后 sync 会重建派生图谱，无需重复语义提取。
更改研究领域、vault、prefix 或 workspace 必须另建实例或进行用户明确要求的数据迁移，不能删除归属文件来绕过检查。
