# CLAUDE.md — comsol-server-mcp

## Project Overview

COMSOL MCP Server (`comsol-mcp` v0.1.9). An attach-first MCP bridge that connects to a running COMSOL Multiphysics Server, loads a main .mph model, locks it, and drives the same server-side model that a COMSOL Desktop client visualizes in real time.

## Architecture

```
comsol_mcp/
  __init__.py              # from .mcp_server import main
  _server.py               # FastMCP instance, global state, constants, classification sets
  _state.py                # Workflow persistence, status/operations logging, path/port utils, _run_tool
  _connection.py           # Disconnect, client shell, _require_client
  _model.py                # Model adopt/prune, visible-main lock mechanism
  _model_ops.py            # Pure helpers: parameters, expressions, core metrics, tree, geometry
  _tools_connection.py     # server_info, check_server_port, server_start, server_connect, server_disconnect
  _tools_workflow.py       # Workflow tools, visible-main lifecycle, model_tree, run_study
  _tools_model.py          # model_create, model_load, prune_loaded_models
  _tools_params.py         # get_parameters, set_parameters, evaluate_expressions, get_core_metrics
  _tools_geometry.py       # ensure_component/geometry/mesh, create/update/delete/run_feature
  _tools_snapshot.py       # run_visible_main_iteration, save_main_model_snapshot, commit_current_main_model, save_model
  mcp_server.py            # Thin entrypoint: imports + register + main()
```

**35 MCP tools** registered via `mcp.add_tool()` in each module's `register()` function.

## Build and Run

```bash
pip install -e .          # install in editable mode
pip install -e ".[dev]"   # with pytest
python -m comsol_mcp.mcp_server   # start MCP server
pytest                           # run tests (40 tests, all without COMSOL)
```

## Module Dependency Graph

```
_server.py  (no deps)
  -> _state.py
    -> _connection.py
      -> _model.py
        -> _model_ops.py (no global state deps)

Tool modules depend on the above:
  _tools_connection -> _server, _state, _connection, _model
  _tools_workflow   -> _server, _state, _model, _tools_connection (cross-module call)
  _tools_model      -> _server, _state, _model
  _tools_params     -> _state, _model, _model_ops
  _tools_geometry   -> _state, _model, _model_ops
  _tools_snapshot   -> _server, _state, _model, _tools_params (cross-module call)
```

No circular imports.

## Key Constraints

- **Windows-only** (COMSOL is Windows)
- **Python 3.10+**
- **35 tools** with stable surface — don't change names or signatures
- **Entrypoint backward compat**: `python -m comsol_mcp.mcp_server`, `from comsol_mcp.mcp_server import main`
- **Visible-main lock**: After `load_visible_main_model()`, tools are guarded by identity check (tag/label/path)
- **Global state**: All mutable state in `_server.py`, guarded by `_runtime_lock` (RLock)

## Tool Classification

| Category | Tools | Behavior when locked |
|---|---|---|
| SAFE_READ | server_info, check_server_port, workflow_info, model_tree, get_parameters, evaluate_expressions, get_core_metrics | Always allowed |
| SAFE_WRITE | set_parameters, ensure_*, create/update/delete/run_feature, run_study, run_visible_main_iteration, save_main_model_snapshot, save_model | Allowed if identity matches |
| RESTRICTED | commit_current_main_model, model_create, model_load, prune_loaded_models | Blocked entirely when locked |

## Cross-Module Tool Calls

Some tools call other tools via direct function call (not MCP dispatch):
- `_start_visible_main_workflow_payload` -> `server_connect`, `load_visible_main_model`, `verify_visible_main_session`
- `run_visible_main_iteration` -> `get_core_metrics`, `save_main_model_snapshot`
- `load_current_main_model` -> `load_visible_main_model`

These are resolved by importing the target function from the other module.

## How to Add a New Tool

1. Add the function to the appropriate `_tools_*.py` module
2. Add `mcp_instance.add_tool(function_name)` to that module's `register()` function
3. If the tool modifies model state, add it to the appropriate classification set in `_server.py`

## How to Add a New Helper

- Pure function (no global state) -> `_model_ops.py`
- State-aware function -> `_state.py` or `_model.py`
- Connection lifecycle -> `_connection.py`

## Testing

- `pytest` runs 40 tests that don't need COMSOL
- Tests cover: sanitize_label, normalize_properties, coerce_eval, last_scalar, port_is_open, workflow_state IO, friendly_connection_error, numeric_result, resolve_path, normcase_path, tool registration, classification sets
- Integration tests requiring a live COMSOL Server are marked `@pytest.mark.comsol_server` and skipped by default
