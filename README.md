# COMSOL MCP

中文 | [English](#english)

`comsol-mcp` 是一个面向 COMSOL Multiphysics 的 MCP Server。它采用
**attach-first** 工作流：先连接到一个已经运行的 COMSOL Multiphysics Server，
再加载并锁定一个主 `.mph` 模型，让 MCP 和 COMSOL Desktop 看到并操作同一个
服务端模型。

这个项目的目标不是把 COMSOL 当成黑盒批处理器，而是让自动化过程保持可见：
你可以在 Desktop 中实时观察 MCP 对几何、参数、网格、求解和保存流程的修改。

## 主要特性

- 连接已有的 COMSOL Multiphysics Server
- 与 COMSOL Desktop 共享同一个服务端模型状态
- 支持 visible-main 主模型锁，避免误切换或误保存模型
- 支持参数设置、表达式求值、几何特征创建/更新/删除、网格和研究运行
- 支持主模型快照、当前模型保存、异步加载大型 `.mph`
- 公开工具接口稳定，目前注册 35 个 MCP tools

## 适用场景

- 需要一边自动化建模，一边在 COMSOL Desktop 中检查模型变化
- 需要让 AI Agent 修改同一个当前主模型，而不是反复启动批处理任务
- 需要保留每次迭代的 `.mph` 快照
- 需要在长时间运行的 COMSOL Server 会话中做参数、几何或求解探索

## 环境要求

- Windows
- Python 3.10 或更高版本
- 本机已安装 COMSOL Multiphysics
- 有效的 COMSOL 许可证
- 手动启动的 `COMSOL Multiphysics Server`

## 安装

```powershell
git clone https://github.com/Ching-Chiang/comsol-mcp.git comsol-mcp
cd comsol-mcp
python -m pip install -e .
```

开发环境可安装测试依赖：

```powershell
python -m pip install -e ".[dev]"
```

## 环境变量

根据你的 COMSOL 安装位置设置：

```powershell
$env:COMSOL_ROOT = "C:\Program Files\COMSOL\COMSOL63\Multiphysics"
$env:COMSOL_SERVER_MCP_HOME = "$PWD\comsol-server-home"
```

`COMSOL_SERVER_MCP_HOME` 用于保存运行状态、日志、输出和快照。该目录默认位于
仓库下的 `comsol-server-home/`，并已被 `.gitignore` 忽略。

## 启动 MCP Server

推荐直接启动长驻 MCP 进程：

```powershell
python -m comsol_mcp.mcp_server
```

也可以使用脚本：

```powershell
.\scripts\start_comsol_mcp.ps1 -Python python -ComsolRoot "C:\Program Files\COMSOL\COMSOL63\Multiphysics" -McpHome "$PWD\comsol-server-home"
```

## MCP 配置示例

Claude Desktop 或其他 MCP host 可以参考：

- `examples/claude_desktop_config.json`
- `.mcp.json`

一个最小配置类似：

```json
{
  "mcpServers": {
    "comsol-mcp-server": {
      "command": "python",
      "args": ["-m", "comsol_mcp.mcp_server"]
    }
  }
}
```

## 推荐工作流

1. 手动启动 `COMSOL Multiphysics Server`。
2. 记录 Server 控制台显示的真实端口。
3. 启动本项目的 MCP Server，并保持进程运行。
4. 调用 `start_visible_main_workflow(host, port, path)`。
5. MCP 连接 Server、加载主 `.mph`，并锁定该 visible-main 模型。
6. 在 COMSOL Desktop 中连接同一个 Server。
7. 在 Desktop 中导入或切换到已经加载的服务端模型。
8. 后续通过 MCP tools 修改模型，并在 Desktop 中观察变化。

大型 `.mph` 如果加载时间超过 MCP host 的单次工具调用超时，使用异步入口。
请把示例路径替换为你本机可访问的 `.mph` 文件：

```text
start_visible_main_workflow_async("localhost", <actual_port>, "C:/path/to/model.mph")
visible_main_workflow_status("<job_id>")
```

## 单主模型配置

如果希望始终围绕一个当前主模型工作，并为每次迭代保存快照：

```text
configure_single_main_workflow(
  "C:/path/to/model.mph",
  "comsol-server-home/snapshots",
  "free_convection"
)
```

常用迭代流程：

```text
verify_visible_main_session()
run_visible_main_iteration("trial_label", "[{\"name\":\"param1\",\"expression\":\"1.0\"}]", "")
save_model()
```

## 工具列表

连接与状态：

- `server_info()`
- `check_server_port(host="localhost", port=2036)`
- `server_start(...)`
- `server_connect(host, port, model_name="")`
- `server_disconnect(shutdown_server=false)`
- `workflow_info()`
- `mcp_tool_audit()`

visible-main 工作流：

- `configure_single_main_workflow(current_main_model_path, snapshot_dir="", snapshot_prefix="", notes="")`
- `start_visible_main_workflow(host="localhost", port=2036, path="")`
- `start_visible_main_workflow_async(host="localhost", port=2036, path="")`
- `visible_main_workflow_status(job_id="")`
- `load_visible_main_model(path="")`
- `verify_visible_main_session()`
- `unlock_visible_main(reason)`
- `load_current_main_model()`

模型与保存：

- `model_create(name="Server Model")`
- `model_load(path)`
- `prune_loaded_models(keep="current")`
- `save_main_model_snapshot(snapshot_label)`
- `commit_current_main_model(snapshot_label="")`
- `save_model(path="")`
- `model_tree()`

参数、表达式与指标：

- `get_parameters()`
- `set_parameters(parameters_json)`
- `evaluate_expressions(expressions_json="[]")`
- `get_core_metrics()`

几何、网格与求解：

- `ensure_component(component="comp1", dimension=2)`
- `ensure_geometry(component="comp1", geometry="geom1", dimension=2)`
- `ensure_mesh(component="comp1", mesh="mesh1")`
- `create_feature(component, geometry, tag, feature_type, properties_json="[]", run_geometry=false)`
- `update_feature(component, geometry, tag, properties_json, run_geometry=false)`
- `delete_feature(component, geometry, tag, run_geometry=false)`
- `run_feature(collection, tag, component="comp1")`
- `run_study(study_tag="")`
- `run_visible_main_iteration(label, parameters_json="[]", study_tag="")`

## visible-main 锁机制

`load_visible_main_model()` 成功后，MCP 会记录模型的 tag、label 和 path。
后续写操作会先检查当前服务端模型是否仍然是这个主模型。

- 安全读工具始终允许执行
- 安全写工具仅在模型身份匹配时允许执行
- `model_create()`、`model_load()`、`prune_loaded_models()`、
  `commit_current_main_model()` 在锁定状态下会被阻止

这个设计用于防止 Desktop 正在查看的主模型被意外切走或覆盖。

## 测试

普通测试不需要 COMSOL Server：

```powershell
pytest
```

带真实 COMSOL Server 的集成测试使用 `comsol_server` 标记，默认跳过。

## 项目结构

```text
comsol_mcp/
  _server.py            # FastMCP 实例、全局状态、工具分类
  _state.py             # 状态持久化、日志、路径和端口工具
  _connection.py        # 连接生命周期与客户端访问
  _model.py             # 模型采用、清理、visible-main 锁
  _model_ops.py         # 参数、表达式、指标、树和几何纯辅助函数
  _tools_connection.py  # 连接相关 MCP tools
  _tools_workflow.py    # 工作流和 visible-main tools
  _tools_model.py       # 模型创建、加载、清理 tools
  _tools_params.py      # 参数、表达式、指标 tools
  _tools_geometry.py    # 组件、几何、网格、特征 tools
  _tools_snapshot.py    # 迭代、快照和保存 tools
  mcp_server.py         # 入口与工具注册
```

## 注意事项

- 本项目不包含 COMSOL 二进制文件或专有模型资源。
- COMSOL Desktop 连接 Server 后，可能需要手动导入或切换到服务端已加载模型。
- `server_start()` 只是高级备用入口；推荐手动启动 COMSOL Server 并使用真实端口连接。
- 保持 MCP 进程长驻，不要用一次性脚本加载模型后立刻退出。

## 联系方式

维护者：mr jiang <jiang-jc24@mails.tsinghua.edu.cn>

## License

MIT. See `LICENSE`.

---

## English

`comsol-mcp` is an MCP server for COMSOL Multiphysics. It uses an
**attach-first** workflow: connect to an already running COMSOL Multiphysics
Server, load and lock a main `.mph` model, and let MCP tools and COMSOL
Desktop operate on the same server-side model.

The goal is visible automation. Instead of treating COMSOL as a black-box
batch runner, this server lets you watch geometry, parameters, mesh, solve
steps, and saved snapshots evolve in COMSOL Desktop.

### Features

- Attach to an existing COMSOL Multiphysics Server
- Share one server-side model with COMSOL Desktop
- Lock the visible main model to prevent accidental model switching
- Set parameters, evaluate expressions, edit geometry features, run mesh and studies
- Save main-model snapshots and handle large `.mph` loads asynchronously
- Stable MCP tool surface with 35 registered tools

### Requirements

- Windows
- Python 3.10+
- Local COMSOL Multiphysics installation
- Valid COMSOL license
- A manually started `COMSOL Multiphysics Server`

### Install

```powershell
git clone https://github.com/Ching-Chiang/comsol-mcp.git comsol-mcp
cd comsol-mcp
python -m pip install -e .
```

For development:

```powershell
python -m pip install -e ".[dev]"
```

### Configuration

Set environment variables for your COMSOL installation:

```powershell
$env:COMSOL_ROOT = "C:\Program Files\COMSOL\COMSOL63\Multiphysics"
$env:COMSOL_SERVER_MCP_HOME = "$PWD\comsol-server-home"
```

Start the MCP server:

```powershell
python -m comsol_mcp.mcp_server
```

Example MCP host configuration:

```json
{
  "mcpServers": {
    "comsol-mcp-server": {
      "command": "python",
      "args": ["-m", "comsol_mcp.mcp_server"]
    }
  }
}
```

### Recommended Workflow

1. Start `COMSOL Multiphysics Server` manually.
2. Note the real listening port from the server console.
3. Keep `python -m comsol_mcp.mcp_server` running.
4. Call `start_visible_main_workflow(host, port, path)`.
5. Connect COMSOL Desktop to the same server.
6. Import or switch to the already loaded server-side model in Desktop.
7. Use MCP tools to modify the locked main model and watch Desktop update.

For large `.mph` files, use the async entrypoint and replace the example path
with a local `.mph` file:

```text
start_visible_main_workflow_async("localhost", <actual_port>, "C:/path/to/model.mph")
visible_main_workflow_status("<job_id>")
```

### Tests

```powershell
pytest
```

The default test suite does not require COMSOL. Integration tests that need a
live COMSOL Server are marked with `comsol_server` and skipped by default.

### Contact

Maintainer: mr jiang <jiang-jc24@mails.tsinghua.edu.cn>

### License

MIT. See `LICENSE`.
