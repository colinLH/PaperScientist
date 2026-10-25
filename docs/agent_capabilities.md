# 专家代理、权限范围与检查扩展

主会话处理用户意图、研究计划与最终整合。复杂环节可委派给文献调研（`literature`）、创新与可行性（`ideation`）、设计实现及单元测试（`design`）、实验评估（`evaluation`）、论文写作（`writing`）和独立审稿（`reviewer`）。简单的直接请求仍可在主会话完成；并非写死的流水线。

文献、构思、设计、实验和写作专家可并行创建 `search` 检索任务或 `general` 通用任务。这两种叶子代理不能再委派；其实际工具和技能是父代理与目标 profile 的交集。`general` 还继承父专家的完成检查。旧名称 `researcher`、`methodologist`、`engineer`、`analyst`、`writer` 保持兼容。独立审稿仍使用不可修改的冻结材料包，不继承项目记忆、其他审稿或父工作区读取权限。

## 权限在哪些位置生效

- 传给 LangChain `bind_tools` 的工具列表已过滤；模型臆造未绑定工具时，调度入口再次拒绝执行。
- 技能目录、检索结果、已激活技能、资源读取和 `stage_skill` 都使用同一个 profile 视图，不能以资源加载绕过技能范围。`@source/` 只提供共享参考资料；遇到另一份 `SKILL.md` 的包边界时，读取和资源列表均拒绝穿越，staging 也不会复制嵌套的其他技能包。
- 子代理默认没有 MCP 权限。主会话仅连接操作者已配置的 MCP；给特定子代理开放 MCP 必须同时满足父代理授权、子 profile 的 `tools` 和 `mcp_tools` 名单。
- 每次委派把具体工具名、技能名、允许子角色及继承检查保存进数据库。重启、继续执行或配置变更不会给已有任务扩大能力；下一次构建任务能力范围时，配置收紧会递归应用到后代。技能文件或对话不能修改 registry。
- 工作文件按 session 隔离；结果通过 artifact ID 显式导入，导入时校验登记的 SHA-256，逐级保留来源。

这是应用层的能力范围，不是操作系统级沙箱。开启本地 Python 执行后，脚本仍以服务进程用户身份运行；面向不可信代码部署时应另外采用容器/操作系统隔离。

## 并行、取消和恢复

`PS_MAX_SUBAGENTS` 限制同时执行的子代理模型或工具操作数，默认 3。等待和派发不占用该名额，因此只设为 1 时，专家等待其子任务也不会死锁。`PS_MAX_AGENT_DEPTH` 默认 2（主代理 → 专家 → 叶子），`PS_MAX_AGENT_TASKS` 默认 64，限制整个研究树累计任务数；达到上限后可继续已有任务。

取消一个代理会递归取消其后代。服务重启将未完成代理标记为 `interrupted`，通过 `followup_task` 恢复原记录和工作区。普通子任务中未通过完成检查的工具证据也会持久保存，下次继续时必须修复，不能靠新开一轮绕过检查。

## 操作者配置

默认定义位于 `paperscientist/agent_profiles.yaml`。可在服务进程的 `PS_AGENT_PROFILES` 环境变量中指定另一个 YAML 文件；它按名称替换默认 profile，并可添加新 profile 或别名。不要把操作者配置存放在某个会话的工作区中。加载发生于服务启动；程序也可显式调用 `service.profiles.reload()`。

例如增加一个只读材料核对角色：

```yaml
version: 1
profiles:
  evidence_reader:
    description: 核对指定材料中的事实
    prompt: 仅核对已提供材料；为每项结论给出文件位置，保留未确定之处。
    tools: [list_files, read_file, copy_parent_artifact, list_skills, load_skill]
    skills: [evidence-review]
    children: []
    harnesses: []
    mcp_tools: []
aliases:
  fact_checker: evidence_reader
```

还需在允许派发它的父 profile 的 `children` 中加入 `evidence_reader`，并保留父 profile 的其他字段；只声明新角色不会自动授权调用。`tools` 和 `skills` 支持明确名称或 glob；推荐给子代理列出具体名称。配置中的 `prompt` 是该角色的 PE；默认共同科研诚信规则继续生效。不存在让对话或技能自行注册角色、执行 Python 插件或提升权限的工具。

## 可执行 harness

应用代码通过 `service.profiles.register_harness(name, callback)` 注册检查。YAML 只能选择已注册的名称和参数，不能动态导入任意 Python。未知检查、检查异常、错误返回结构或 `ok: false` 都阻止相应操作或完成状态。

```python
async def check_references(phase, context, rule):
    # 必须依据实际文件/执行记录检查；不要将模型自报当作证据。
    return {"ok": True, "reason": "..."}

service.profiles.register_harness("check_references", check_references)
```

回调签名为 `(phase, context, rule)`，可以是同步或异步函数。`phase` 为 `before_tool`、`after_tool`、`completion`。`context` 提供 `service`、`store`、`session`、`settings`、`profile`、`actions`（每项含 `name/input/result/status`）；工具阶段另有 `tool_name`、`input/tool_input`、`result/tool_result`，完成阶段有 `answer`，持久运行还提供 `run_id` 和交付文件。`rule` 是 YAML 中该检查的整项配置。

内置 `implementation_tests` 在设计代理写入、导入或生成 Python 后要求最新修改之后存在成功且非空的 unittest/pytest 运行记录。可信启动器 `test_execution.py` 观察进程内真实框架事件，将测试数、失败数和被测源码哈希写入执行收据的 `unit_tests`；完成检查还核验收据 SHA-256、runner 和被测代码是否保持原样。动态导入包装 runner 受支持，不要求固定文件名或直接 import 文本。仅打印“测试通过”、没有实际测试、进程退出 0 但测试失败，以及负对照触发的预期失败，都不能冒充正向通过。负对照中新写了 Python 后，需要再次运行正向测试；失败诊断会给出最后改动、后续运行和建议入口。

子进程 stdout 不自动认证。若测试由另一个 Python 进程执行，应在 `run_python` 的当前进程内运行 `unittest.TextTestRunner`/discovery 或 `pytest.main` 来生成可验证的框架事件。被测源码还必须匹配执行前快照、观察到的版本和完成检查时的版本；一次运行中新生成或修改了 Python，需要保存后再跑正向测试。旧版文本收据保留为历史材料，重新执行会产生事件收据。这些检查确认执行和文件一致性，不能证明测试覆盖充分，也不是针对恶意 Python 反射/篡改的安全隔离机制。

`manuscript_layout` 检查论文版式；`benchmark_evidence` 检查已选实验协议的执行证据。主代理直接产出论文或实验结果时同样应用后两者。失败的完成检查允许模型在剩余预算内修复，连续失败会返回明确未完成状态，保留文件供继续。

回归入口：`python -m pytest tests/test_agent_profiles.py tests/test_research_agent.py tests/test_skill_integration.py tests/test_mcp_and_failures.py -q`。
