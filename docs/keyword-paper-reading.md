# 关键词论文精读 → Obsidian

从 `/welcome` 最后一幕点击 **关键词论文精读 → Obsidian**，或直接访问 `/reading`。输入主题、选择 1–4 篇（默认 2 篇），点击开始后执行一次检索和精读。页面提供持久化进度、停止/继续、问题回答、历史报告搜索、Markdown 预览/下载、PDF 与原图及 Obsidian 链接。关闭浏览器不会停止任务。

这是从既有“AI 安全论文日报 → Obsidian”提取的按需精读流程；不创建、修改或替代 Codex 中的每日定时任务，也不发送跨聊天消息。关键词控制本轮选题。既有 Obsidian 报告可直接阅读。

## 本地归档配置

在精读页面点击 **连接 / 切换 Obsidian**，选择自动发现的仓库，或粘贴本机已有文件夹的绝对路径。发现功能读取当前用户的 Obsidian 注册文件，支持 macOS、Windows、Linux 和 Flatpak；未安装 Obsidian 也可手动选择 Markdown 文件夹。路径来自使用者的电脑，不包含原作者的仓库位置。

选择读取与归档的子目录（如 `AI安全`、`论文`，或用 `.` 选择整个仓库），勾选导入已有 Markdown，点击 **预览导入**，确认数量与标题后 **保存并连接**。立即生效，无需重启；刷新书架会重新读取本地新增或修改的笔记。这里的“本机”指运行 PaperScientist 服务的电脑，远程浏览器不会自动上传它所在电脑的笔记。

导入直接读取原文件，不复制或改写个人笔记。书架支持标准 Markdown、本地图片与相对或仓库根目录的 `[[路径|别名]]` / `![[图片路径]]`，跳过隐藏目录、系统目录、符号链接及超过 2 MB 的笔记；范围超过 2000 篇时请改选子目录。跨出所选子目录的附件不提供预览，可改选共同上级或整个仓库。

普通笔记仅供阅读；frontmatter 中的 `paper_title`、`type: paper` 配合 `title`，或有效的 `arxiv_id` / `doi` 用于识别已有论文。正文引用不算已归档论文。导入身份只用于动态去重，不写入或替代 `系统/collection-index.json`，也不代表精读质量已经核验。原有索引及未知字段保留；旧格式 `01-报告` 存在但索引缺失时，须先恢复索引。

设置保存在当前安装的 `PS_DATA_DIR/reading-config.json`（默认 `.paperscientist/reading-config.json`，不提交 Git）：

```json
{
  "vault_root": "/absolute/path/to/your/obsidian/vault",
  "prefix": "AI安全",
  "include_existing_notes": true
}
```

Windows 可使用 `"E:/notes/paper"`。页面保存立即生效；仅手动编辑配置文件时需要重启服务。未配置时使用本安装数据目录下的 `reading-vault/AI安全`，首次归档时创建。配置损坏时显示原因，可从页面重新连接，不影响论文产出服务。

活动精读任务执行期间不能切换仓库。每个任务持久保存其原始归档位置；切换后的任务列表只显示对应仓库的历史，切回即可继续旧任务。模型工具、归档门禁和导出都使用任务绑定的位置，重启后仍保持一致。

新报告沿用 `01-报告`、`附件/PDF`、`附件/图表/YYYY-MM-DD`、`附件/资料` 与 `系统/collection-index.json`。保留稳定 `source_id`、`complete: true`、本地引用及图像来源清单；索引新条目为 `awaiting_graph`，供现有图谱任务增量处理。原报告和个人笔记不被覆盖。旧报告若没有 `complete` 字段，页面不将其误标为草稿。

## 执行与隔离

- `ReadingService` 复用已配置的模型与持久执行机制，数据、会话、项目、草稿、检查点均在 `PS_DATA_DIR/reading/`，与论文产出任务的数据库和工作区分离。
- 专用 `paper_reader` 配置在模型绑定和工具执行两处生效。仅有文献搜索、受限来源读取、PDF 提取/原图捕获、完整报告归档与进度工具；没有 Python 执行、任意文件写入、MCP、子代理、实验或 LaTeX 产出能力。技能目录按角色过滤，恢复任务仍使用同一角色和验收规则。
- 每轮目标篇数必须全部达到才可通过归档验收；来源不足、错误或模型预算耗尽时保留草稿与证据，可继续处理。演示模式不能假称收集成功。当前界面一次允许一个活动精读任务（单服务进程部署）。
- 不增加模型密钥。无网页搜索密钥时仍可使用 arXiv / OpenAlex / Crossref 和公开来源读取。

## 证据与完成条件

PDF 从公开地址获取并记录 SHA-256。分段输出限制长度，逐页记录实际返回的字符区间；长页面通过 `next_read` 继续，不能因工具输出被截断而把未返回部分算作已读。报告提交需覆盖全文，题名需匹配原文前两页，截图需来自本任务已登记且未被修改的原文。

报告包含摘要、背景、动机与挑战、解决措施与贡献、设计框架及创新细节、各维度实验与消融、局限、研究联系和来源。每张原图保存物理页码、原图编号、中文图注、解释和固定版本 URL；以原 PDF 页面截图保留上下文。不生成替代图。无法取得相关图时须说明实际原因。

当前模型阅读的是 PDF 提取文本；页面截图不等于视觉模型已判读图表。报告明确披露这一点。提示要求图例、方法和柱值不能明确对应时保留原图并标记待视觉核实，不按文本提取顺序猜测数值。程序验收能证明来源文件、覆盖、结构与引用的完整性，不能证明模型对每个科学结论的解释都正确。无可提取文本的扫描 PDF 不会假装完成全文阅读。

归档与现有 `obsidian_sync.py` 共用 `系统/.sync.lock`。规范 arXiv ID（去版本号）、DOI、完整标题和已核对别名用于全量去重，`awaiting_graph` 也算已归档。提交前再查一次累计索引；保留已有记录及未知字段，原子替换索引。先写带哈希的恢复回执，再提交索引，重试不会重复增加论文。索引缺失但已有报告时停止收集，不将其误判为空仓库。

`reading_archive` 完成门禁重新核验归档文件哈希和索引；模型调用 `finish_research` 也不能绕过。停止或重启会保留持久运行状态；中断中的工具不会被盲目重复执行，需检查已有结果后继续。工作区同时保存带本地附件的报告副本。

## 验证

```bash
python -m pytest tests/test_reading.py tests/test_obsidian_vaults.py tests/test_agent_profiles.py tests/test_durable_harnesses.py tests/test_durable_runs.py tests/test_intro.py tests/test_research_agent.py -q
node --test tests/intro_closing.test.mjs tests/intro_journey.test.mjs tests/intro_motion.test.mjs
```

浏览器验证需本地 Chrome、Playwright 和至少一份带本地图片的历史报告：

```bash
READING_BASE_URL=http://127.0.0.1:8888 node tests/reading_browser.cjs
```

如 Playwright 未装在项目中，可通过 `PLAYWRIGHT_MODULE` 指定现有模块目录。截图写入忽略的 `.test-output/reading`；按钮执行、停止、继续与待回答状态使用浏览器拦截响应，不会启动真实收集。真实模型试跑与合成归档测试分别记录；二者都不代表官方科学基准结果。
