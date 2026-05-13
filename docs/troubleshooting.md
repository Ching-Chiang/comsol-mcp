# Troubleshooting

## Connected, but Desktop is empty

- In visible-main mode, MCP should load the main `.mph` first with
  `start_visible_main_workflow(host, port, path)`.
- Then connect Desktop to the same server and import the already loaded server
  model instead of keeping a local empty view.
- If Desktop opened the wrong model, disconnect/reconnect Desktop and choose
  the existing locked main model from the server.

## COMSOL Server exits after MCP loads the model

For visible-main work, MCP must stay alive as a persistent control process.
Do not use an ad-hoc one-shot Python script that imports `comsol_mcp.mcp_server`,
connects, loads the MPH, and exits. That script also tears down its Java API
client when Python exits, and some manually started COMSOL Server sessions may
shut down or become unstable before Desktop imports the model.

Use `scripts/start_comsol_mcp.ps1` or the configured MCP server entrypoint and
keep that process running while Desktop connects/imports and while iterations
are executed.

## Loading the main MPH exceeds the MCP tool timeout

Use the asynchronous visible-main entrypoint:

- `start_visible_main_workflow_async(host, port, path)`
- `visible_main_workflow_status(job_id)`

This starts loading inside the persistent MCP process and returns a job id
quickly, so the MCP host can poll instead of timing out the live load call.

## `server_connect()` succeeds, but no model is selected

This means MCP is attached to the server, but no current working model is selected.
Use:

- `load_visible_main_model("path/to/current_main.mph")`

In strict visible-main mode, use `model_create()` and `model_load()` only before
the visible main lock is enabled, or after an explicit `unlock_visible_main(reason)`.

## Snapshot save changes the Desktop model name

Use `save_main_model_snapshot()` or `run_visible_main_iteration()`. These tools
use COMSOL's save-copy API, so the snapshot file is written without remembering
that snapshot path as the current model path.

If the Desktop title still changes to a snapshot name:

- call `verify_visible_main_session()`
- confirm `identity.path` is the current main `.mph`
- avoid loading snapshot files with `model_load()`
- unlock only for maintenance with `unlock_visible_main(reason)`

## Connection refused

`Connection refused` usually means there is no live `COMSOL Multiphysics Server`
listening on the requested port. It is not necessarily a password problem.

In the fixed visible workflow, call:

- `check_server_port(host, port)`
- or `start_visible_main_workflow(host, port, path)`

If the port is not live, MCP should tell you to manually start COMSOL Server
and provide the actual port. MCP should not silently start a fallback server in
this workflow.

## The server console says one port, but the actual listener is different

Always trust the real listener:

- the COMSOL server console output
- or OS tools such as `netstat`

Desktop and MCP must attach to the same real listening port.

## Desktop does not immediately redraw after a model change

The server-side model is still updated. Try:

- selecting `geom1`
- selecting `mesh1`
- refreshing the graphics view

If the model tree already shows the updated objects, the data layer is in sync.
