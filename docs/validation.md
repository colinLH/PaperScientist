# 验证报告

验证时间：2026-10-23（Asia/Shanghai）。真实模型：`deepseek:deepseek-chat`。使用用户提供的凭据，仅通过测试进程和本地验证服务的环境传入，没有把密钥写入源码、报告或聊天数据库。

## 自动化测试

命令：`D:/anaconda3/envs/llm/python.exe -m unittest discover -s tests -v`

最终结果：**20 / 20 通过**，约 8 秒。覆盖：

- 追加历史、记忆版本/来源/作用域、automation 注入门槛、路径约束。
- 多轮动态工具调用、中断工具配对修复、预算停止状态。
- Micro compact 的调用/结果配对与继续回合保留；sync summary 原文保留与恢复；摘要失败不提交 checkpoint。
- 真实 Python 子进程、结果 hash 防篡改、生成文件登记、执行前脚本 hash、实际 matplotlib PNG/PDF/SVG 输出、中文字体。
- LaTeX 引用来源检查、缺失章节/图片/引用/label 检查。
- 独立子代理、续跑、取消、进程重启恢复；技能跨大量事件恢复。
- **真实 stdio MCP** 的发现和调用，嵌套 schema 与非法参数验证。
- FastAPI SSE、会话、上传、下载、导出、Gradio 挂载；离线历史提炼的 dry-run 与原文证据约束。

Windows / Gradio 测试过程中有 `ResourceWarning: unclosed event loop`，未造成断言失败。这项依赖资源清理告警仍保留在日志中，没有用过滤器隐藏。

## DeepSeek 真实端到端运行

测试会话：`live_1792686390323001200`。数据全部位于 `.test-output/deepseek-live/`，与默认业务数据目录分开。

1. 用户说明 ML / agent-memory 兴趣、中文协作偏好和 CPU 限制：模型调用 remember 保存有原文证据的画像与项目记忆，提出候选方向与问题。
2. 用户选择“长对话记忆压缩中的证据保留”：模型确认方向、建立计划和贡献—评估问题，生成并执行标准库实验。运行产生 5 seeds 的原始 CSV、聚合 CSV、元数据、带 synthetic 声明的图和框架图。实验明确登记为 synthetic。
3. 模型检索 Crossref 真实论文元数据，启动独立审查任务，生成带真实检索引用 ID 的多文件英文 LaTeX 草稿。第一次复杂回合触发 24 步预算，未假装任务完成。
4. 修复验证暴露的问题后，在**同一个持久会话**恢复执行。DeepSeek 重新生成图，使用 `role=reviewer` 的子代理审查文件与证据，纳入意见，检查稿件、尝试编译并导出 ZIP。本次没有工具错误，最终 `stop_reason=completed`。

恢复验证的六项检查全部通过：会话完成、图表登记、reviewer 完成、稿件完整性、ZIP 生成、实际检查编译器可用性。稿件静态检查覆盖 **10 个 TeX 文件与 2 个引用键**。

独立的长历史测试使用真实 DeepSeek 触发 sync summary：原始 **17 条消息保持不变**，模型上下文变为 **5 条消息**；恢复后正确回答 CPU-only 约束，并明确拒绝将合成数据解释为真实科研性能。

原始报告保留在：

- `.test-output/deepseek-live/report.json`：第一次三轮运行，包含原始失败与预算终止。
- `.test-output/deepseek-live/resume-report.json`：修复后恢复验证及最终答案。
- `.test-output/deepseek-live/visual-fix.json`：最后视觉检查的修订与最终 bundle ID。

## 验证发现与修复

| 发现 | 修复与证据 |
|---|---|
| Memory INSERT 占位符数量不符 | 修复 SQLite 写入；记忆与多轮回归通过 |
| 自定义 Python 生成的图未自动进入产物列表 | 捕获常见生成文件及 hash，登记运行来源；真实 DeepSeek 重跑后产物可见 |
| 子代理 task_name 约束未充分暴露给模型 | schema 增加 pattern 与示例，role 改为枚举；恢复运行成功创建 reviewer |
| 单轮预算结束容易与完成混淆 | 返回 stop_reason，子任务对应 interrupted，Web 显示可继续 |
| 已加载技能可能被后续大量工具事件挤出窗口 | 独立按 skill_loaded 查询与去重；新增恢复测试通过 |
| 中文框架图缺字，像素尺度坐标让节点框过小 | 本地 CJK 字体、坐标归一化、节点自适应换行与边界箭头；实际渲染检查 |
| 样例自定义图的标题与 synthetic 标注重叠 | 视觉检查后调整样例 Python 排版与指标文字，保留数值；重新运行、复制与打包 |

最后一项是人工视觉审查后的样例修订，不计作 DeepSeek 自动视觉理解的结果。当前 DeepSeek 配置没有视觉模型；框架图通用工具已改进，复杂自定义图仍需视觉审查或接入适当的视觉 MCP 工具。

## 编译与范围限制

运行环境 PATH 未发现 Tectonic / pdfLaTeX；应用的 compile_latex 正确返回 `unavailable`。随后尝试 Codex 编辑器内置编译器，结果为 **Compilation timed out**。因此只确认源码完整性，**没有确认整篇论文 PDF 编译通过**。源码与图表已完整保存，安装可用 TeX 编译器后可继续检查。

Crossref 使用真实网络；通用 Web 搜索的 Tavily / SerpAPI、远端 HTTP MCP、其他模型供应商和实际 GPU 实验未作线上验收。stdio MCP 已实际验证。首次运行检索到的论文仅作为元数据引用，不代表已阅读全文或确认新颖性。

这次实验是软件验收用的合成任务，不能支持真实科学性能、统计显著性或投稿质量结论。子代理明确指出 full 与 recent-k 非预算对齐、部分数值是生成器结构导致的恒等式，稿件已纳入这些限制。

## Web 复核

已在实际浏览器打开并操作 Web：新建/恢复会话、发送消息、流式显示与切换状态面板。自动化接口还验证了上传、产物下载和会话导出。最终本地验证服务位于 `http://127.0.0.1:8888`，使用 DeepSeek 和上述验证数据目录；默认代码执行关闭，可在界面中按需启用。

浏览器实测还确认：清空对话创建新的 session ID，旧会话仍可恢复；最新稿件 ZIP 排在下载列表首位，图表预览使用完整缩放。Web 中的真实 DeepSeek 回复已显示，截图保存在 `.test-output/web-preview.png`。

重新启动普通业务实例时，按 README 配置环境；默认数据目录为 `.paperscientist`，不会自动混入这些验收数据。
# 视频 Skills 集成补充验证（2026-10-23）

本次在此前验证基础上完成 382 个外部技能包的固定版本下载，配合 11 个原生技能，
共 393 项。来源和校验值见 [版本清单](video-skills.lock.json)，逐项解析见
[视频分析与集成说明](video-skills-analysis.md)。

- 全部 27 项自动测试通过；随后对审稿压缩恢复边界的 7 项针对性回归测试通过。
- DeepSeek 两轮真实调用均 completed，17 次工具调用无失败，8 项断言全部通过。
- 真实产物包括 .drawio、PNG/PDF/SVG、figure_contract、精确引文证据和 research_audit。
- 合成数据保持 synthetic，审计保持 needs_review，不宣称已验证真实科研性能。
- 隔离审稿测试验证白名单源文件快照、父状态/画像隔离、压缩恢复隔离和不可覆写评审源材料。
- 实际浏览器验证了技能库总数、中文查询和正文加载；截图位于
  ../.test-output/video-skills/web-skills.png。

报告与日志保存在 .test-output/video-skills/。本次没有运行全部第三方脚本或配置全部
外部服务；SciPlot 的 Python 3.14 运行时未安装，采用原生绘图适配。

# 项目会话界面验证（2026-10-23）

- `python -m unittest discover -s tests -v`：33 项通过；最终取消与界面挂载相关的 7 项再次通过。
- DeepSeek 真实调用：同项目两个会话、共三轮；首问概括为“长期科研Agent项目记忆计划”，追问后标题保持不变，会话摘要更新到 v2。第二个会话无需旧原文，即可准确复述 CPU 和三个种子约束，并区分助手提议与未验证结果。11 项程序断言全部通过，记录在 `.test-output/workspace-live-report.json`。
- 浏览器验证：中文项目创建、展开/搜索侧栏、同会话追问、历史切换、输入栏模型选择、加号上传及预览、附件发送后清理、项目记忆卡片。旧会话已通过标题补齐脚本生成首问概括。
- 取消修复覆盖实际模型任务和待消费事件队列，UI 使用每个浏览器会话独立的响应代次拦截过期输出；停止/切换保留落盘历史。模型 token 的界面刷新合并到最多每 100ms 一次，避免每个 token 重建控件。
- 验证项目与示例数据明确用于界面/记忆机制测试，不构成科研实验结果。
- 界面截图：`.test-output/workspace-final.png`、`.test-output/workspace-memory-final.png`。四次临时取消探针已从活跃列表移出，数据库完整备份保存在 `.test-output/workspace-cancel-probes-backup.db`，可核对取消事件；两个跨会话验证对话继续保留供查看。

## 侧栏右键菜单验证（2026-10-23）

- 回归新增 6 项，覆盖元数据重启持久化、项目/会话归档及恢复、工具调用成对复制与附件独立性、跨用户/项目删除隔离、全部关联记忆版本清理、分享快照转义及撤销、运行中删除取消任务，以及实际 Gradio 回调的当前选择切换与归档只读。原有 33 项保持通过。
- 浏览器在独立测试数据目录验证项目与会话右键、重命名、置顶、未读、分区、分叉、分享链接复制、新窗口深链接、归档恢复、键盘快捷键、永久删除确认的范围展示和取消。永久删除执行通过隔离数据库和真实 UI 回调测试完成，未删除已有用户会话。
- 真实 `deepseek:deepseek-chat` 两轮验证：原会话给出测试代号“青竹17”；复制完整历史后的分叉准确回复该代号，原会话消息数量保持不变，手工标题未被模型覆盖，归档恢复保留历史。报告：`.test-output/context-menu-deepseek-report.json`。
- 主工作区数据库升级前已备份，版本仅新增导航、分享与删除墓碑表。实际菜单截图：`.test-output/context-menu-final.png`；测试日志：`.test-output/context-menu-all-tests.log`、`.test-output/context-menu-tests.log`。
