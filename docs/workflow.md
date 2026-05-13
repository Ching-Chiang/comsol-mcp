# Attach-First Workflow

`comsol-mcp` is built around a shared COMSOL server model:

1. Start `COMSOL Multiphysics Server` manually.
2. Confirm the real listening port from the server console or OS network tools.
3. Start MCP as a persistent process, for example with
   `scripts/start_comsol_mcp.ps1`.
4. Call `start_visible_main_workflow(host, port, path)` from that persistent MCP process.
5. If the port is not listening, create a manual COMSOL Server and provide the actual port to MCP.
6. If the port is listening, MCP connects, loads, and locks the main `.mph`.
7. Keep the MCP process running.
8. Connect COMSOL Desktop to that same port.
9. Import the already loaded server-side model into the current Desktop window.
10. Run modeling tools through MCP and watch the same locked main model update in Desktop.

Why this is the recommended path:

- The server login is explicit and controlled by the user.
- Desktop and MCP operate on the same server-side model.
- The workflow is visible and not a black-box batch pipeline.
- It avoids GUI automation and Desktop-side polling bridges.
- Save-copy snapshots preserve evidence without changing the Desktop-visible
  model path or switching the current model to a snapshot.
- A persistent MCP process avoids tearing down the Python/JVM API client between
  loading the main model and Desktop importing it.

Do not use a one-shot Python script as the live control surface for this
visible-main workflow. Such scripts exit immediately after their call, which
also tears down their Java API client and can destabilize some manually started
COMSOL Server sessions before Desktop has imported the model.

## Visible Main Lock

After `load_visible_main_model(path)`, MCP records the main model tag, label,
and file path in `workflow_state.json`. In strict mode, tools that can switch
the active model, such as `model_load()`, `model_create()`, and
`commit_current_main_model()`, plus public cleanup calls such as
`prune_loaded_models()`, are blocked until `unlock_visible_main(reason)` is
called for maintenance.

The fixed startup command is:

```text
start_visible_main_workflow("localhost", <actual_port>, "C:/path/to/model.mph")
```

If loading the main `.mph` can exceed the MCP host's tool timeout, use the
asynchronous variant instead:

```text
start_visible_main_workflow_async("localhost", <actual_port>, "C:/path/to/model.mph")
visible_main_workflow_status("<job_id>")
```

If the port is not live, MCP returns a user-facing instruction to manually start
COMSOL Server and provide the actual port. MCP does not silently start a server
in this visible workflow.

The usual iteration sequence is:

```text
verify_visible_main_session()
run_visible_main_iteration("trial_label", "[{\"name\":\"param1\",\"expression\":\"1.0\"}]", "")
verify_visible_main_session()
```

The snapshot written by the iteration is a copy, not a new current model.
