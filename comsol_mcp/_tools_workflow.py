#!/usr/bin/env python3
"""MCP tools: workflow_info, configure, visible-main workflow tools, load, verify, unlock, audit, async."""

from __future__ import annotations

import json
import threading
import logging
from typing import Any

import comsol_mcp._server as _srv
from comsol_mcp._state import (
    _run_tool, _run_tool_readonly, _json, _now_iso, _resolve_path, _resolve_output_path,
    _read_workflow_state, _write_workflow_state,
    _append_operation, _status_payload, _setup_logging,
    _port_is_open, _server_missing_guidance, _mark_awaiting_manual_server,
    _safe_model_label, _safe_model_path, _safe_model_tag,
    _resolved_model_file_path, OUTPUTS_DIR, OPERATIONS_FILE, SERVER_LOG,
    _create_background_job, _update_background_job, _read_background_job,
    _sanitize_snapshot_label,
)
from comsol_mcp._connection import _require_client, _timed_call
from comsol_mcp._model import (
    _set_current_model, _require_visible_main, _require_model,
    _block_if_visible_main_locked, _adopt_model_by_path,
    _prune_loaded_models_locked, _visible_main_identity,
    _visible_main_mismatch, _visible_main_lock_enabled,
    _loaded_model_records_locked,
)


def workflow_info() -> str:
    """Return the persisted MCP workflow policy for current-main-model operation."""

    def _impl() -> dict[str, Any]:
        return {"workflow": _read_workflow_state()}

    return _run_tool_readonly("workflow_info", _impl)


def configure_single_main_workflow(
    current_main_model_path: str,
    snapshot_dir: str = "",
    snapshot_prefix: str = "",
    model_dimension: int = 0,
    notes: str = "",
) -> str:
    """Persist the single-current-main-model workflow in MCP state.

    model_dimension: spatial dimension of the model (2 or 3). Set to 0 to
    skip. This is used by create_physics and evaluate_expressions aggregate
    to select the correct COMSOL node types. For 2D models set to 2, for 3D
    set to 3.
    """

    def _impl() -> dict[str, Any]:
        current_main = _resolve_output_path(
            current_main_model_path,
            OUTPUTS_DIR / "current_main_model.mph",
        )
        snapshot_root = ""
        if str(snapshot_dir or "").strip():
            snapshot_root = str(_resolve_output_path(snapshot_dir, current_main.parent))
        prefix = snapshot_prefix.strip() or current_main.stem
        dim = int(model_dimension)
        workflow = _write_workflow_state(
            {
                "mode": "single-current-main-model",
                "current_main_model_path": str(current_main),
                "snapshot_dir": snapshot_root,
                "snapshot_prefix": prefix,
                "snapshot_name_template": "{prefix}_{label}_{timestamp}.mph",
                "visible_main_locked": False,
                "guard_level": "strict",
                "snapshot_save_mode": "copy",
                "main_model_tag": "",
                "main_model_label": "",
                "main_model_path": str(current_main),
                "model_dimension": dim,
                "workflow_stage": "mcp_connected",
                "notes": notes.strip()
                or "Operate on one visible current main model; save copy snapshots without changing the visible model identity.",
            }
        )
        return {"workflow": workflow}

    return _run_tool("configure_single_main_workflow", _impl)


def load_visible_main_model(path: str = "") -> str:
    """Load or adopt the visible main MPH, then lock MCP to that server-side model."""

    def _impl() -> dict[str, Any]:
        client = _require_client()
        workflow = _read_workflow_state()
        requested = str(path or workflow.get("current_main_model_path", "") or "").strip()
        if not requested:
            raise RuntimeError("No visible main model path was provided or configured.")
        resolved = _resolve_path(requested)
        model = _adopt_model_by_path(str(resolved))
        origin = "visible-main-adopted"
        if model is None:
            model = _timed_call(
                client.load, resolved,
                timeout=300.0,
                error_msg=f"Loading model {resolved} timed out after 300s. Use start_visible_main_workflow_async for large models.",
            )
            origin = "visible-main-loaded"
        _set_current_model(model, origin=origin, requested_path=str(resolved))
        removed, kept = _prune_loaded_models_locked(model)
        identity = _visible_main_identity(model)
        workflow = _write_workflow_state(
            {
                "mode": "single-current-main-model",
                "current_main_model_path": str(resolved),
                "visible_main_locked": True,
                "guard_level": "strict",
                "snapshot_save_mode": "copy",
                "main_model_tag": identity["tag"],
                "main_model_label": identity["label"],
                "main_model_path": identity["path"] or str(resolved),
                "workflow_stage": "visible_main_locked",
                "last_action": "load_visible_main_model",
                "last_loaded_main_model_path": str(resolved),
                "last_loaded_at": _now_iso(),
                "last_prune_keep_mode": "visible-main",
                "last_prune_kept_tag": identity["tag"],
                "last_prune_removed_count": len(removed),
                "last_prune_at": _now_iso(),
            }
        )
        _append_operation(
            {
                "event": "visible_main_locked",
                "load_mode": origin,
                "identity": identity,
                "removed_loaded_models": removed,
            }
        )
        return {
            "label": identity["label"],
            "tag": identity["tag"],
            "file_path": identity["path"],
            "requested_path": str(resolved),
            "load_mode": origin,
            "removed_loaded_models": removed,
            "remaining_loaded_models": kept,
            "workflow": workflow,
            "desktop_next_step": "Connect COMSOL Desktop to the same server and import the already loaded server model.",
        }

    return _run_tool("load_visible_main_model", _impl)


def verify_visible_main_session() -> str:
    """Verify that MCP is still operating on the locked visible main model."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("verify_visible_main_session")
        workflow = _read_workflow_state()
        return {
            "visible_main_locked": bool(workflow.get("visible_main_locked")),
            "guard_level": workflow.get("guard_level", ""),
            "snapshot_save_mode": workflow.get("snapshot_save_mode", ""),
            "identity": _visible_main_identity(model),
            "loaded_models": _loaded_model_records_locked(),
            "mismatches": _visible_main_mismatch(model, workflow),
            "workflow": workflow,
        }

    return _run_tool("verify_visible_main_session", _impl)


def unlock_visible_main(reason: str) -> str:
    """Unlock the visible-main guard for explicit maintenance actions."""

    def _impl() -> dict[str, Any]:
        explanation = str(reason or "").strip()
        if not explanation:
            raise ValueError("reason is required to unlock the visible main workflow.")
        workflow = _write_workflow_state(
            {
                "visible_main_locked": False,
                "workflow_stage": "visible_main_unlocked",
                "last_action": "unlock_visible_main",
                "last_unlock_reason": explanation,
                "last_unlock_at": _now_iso(),
            }
        )
        _append_operation(
            {
                "event": "visible_main_unlocked",
                "reason": explanation,
                "current": _visible_main_identity(_srv._current_model),
            }
        )
        return {"unlocked": True, "reason": explanation, "workflow": workflow}

    return _run_tool("unlock_visible_main", _impl)


def mcp_tool_audit() -> str:
    """Return the visible-main safety classification for the MCP tool surface."""

    def _impl() -> dict[str, Any]:
        return {
            "guard_level": _read_workflow_state().get("guard_level", "strict"),
            "workflow_tools": [
                "configure_single_main_workflow",
                "check_server_port",
                "start_visible_main_workflow",
                "start_visible_main_workflow_async",
                "visible_main_workflow_status",
                "load_visible_main_model",
                "verify_visible_main_session",
                "unlock_visible_main",
                "mcp_tool_audit",
            ],
            "safe_read_tools": sorted(_srv.SAFE_READ_TOOLS),
            "safe_visible_main_write_tools": sorted(_srv.SAFE_VISIBLE_MAIN_WRITE_TOOLS),
            "restricted_tools": sorted(_srv.RESTRICTED_TOOLS),
            "restricted_policy": "Blocked while visible_main_locked=true and guard_level=strict.",
        }

    return _run_tool("mcp_tool_audit", _impl)


def model_tree() -> str:
    """Return tags and structure for the current server-side model."""

    def _impl() -> dict[str, Any]:
        from comsol_mcp._model_ops import _model_tree_data
        return _model_tree_data(_require_visible_main("model_tree"))

    return _run_tool_readonly("model_tree", _impl)


def run_study(study_tag: str = "") -> str:
    """Run the current model study, optionally restricting execution to a study tag."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("run_study")
        study = study_tag.strip()
        if study:
            try:
                label = str(model.java.study().get(study).label())
                model.solve(label)
            except Exception:
                model.solve(study)
        else:
            model.solve()
        return {"study_tag": study, "label": _safe_model_label(model)}

    return _run_tool("run_study", _impl)


# ---------------------------------------------------------------------------
# Orchestration helpers (internal, not registered as tools)
# ---------------------------------------------------------------------------
def _start_visible_main_workflow_payload(
    host: str = _srv.DEFAULT_HOST,
    port: int = _srv.DEFAULT_PORT,
    path: str = "",
    *,
    action: str,
) -> dict[str, Any]:
    from comsol_mcp._tools_connection import server_connect

    requested_host = host or _srv.DEFAULT_HOST
    requested_port = int(port)
    if not _port_is_open(requested_host, requested_port):
        workflow = _mark_awaiting_manual_server(requested_host, requested_port, action)
        return {**_server_missing_guidance(requested_host, requested_port), "workflow": workflow}

    _write_workflow_state(
        {
            "last_action": action,
            "last_visible_workflow_host": requested_host,
            "last_visible_workflow_port": requested_port,
            "workflow_stage": "mcp_connecting",
            "mcp_client_lifecycle": "persistent-required",
            "one_shot_client_allowed": False,
        }
    )
    connect_payload = json.loads(server_connect(requested_host, requested_port, ""))
    if not connect_payload.get("success", False):
        raise RuntimeError(connect_payload.get("error", "server_connect failed"))
    workflow = _read_workflow_state()
    requested_path = str(path or workflow.get("current_main_model_path", "") or "").strip()
    if not requested_path:
        raise RuntimeError("No main MPH path was provided or configured for visible workflow startup.")

    _write_workflow_state(
        {
            "last_action": action,
            "workflow_stage": "visible_main_load_in_progress",
            "visible_main_load_started_at": _now_iso(),
        }
    )
    load_payload = json.loads(load_visible_main_model(requested_path))
    if not load_payload.get("success", False):
        raise RuntimeError(load_payload.get("error", "load_visible_main_model failed"))

    _write_workflow_state(
        {
            "last_action": action,
            "workflow_stage": "visible_main_verify_in_progress",
        }
    )
    verify_payload = json.loads(verify_visible_main_session())
    if not verify_payload.get("success", False):
        raise RuntimeError(verify_payload.get("error", "verify_visible_main_session failed"))
    workflow = _write_workflow_state(
        {
            "last_action": action,
            "last_visible_workflow_host": requested_host,
            "last_visible_workflow_port": requested_port,
            "last_visible_workflow_started_at": _now_iso(),
            "workflow_stage": "desktop_import_expected",
            "mcp_client_lifecycle": "persistent-required",
            "one_shot_client_allowed": False,
        }
    )
    return {
        "server_available": True,
        "connected": True,
        "host": requested_host,
        "port": requested_port,
        "main_model": load_payload.get("data", {}),
        "verification": verify_payload.get("data", {}),
        "workflow": workflow,
        "next_step_for_user": (
            "Open COMSOL Desktop, connect it to this same server, and import/select "
            "the already loaded main model in the current Desktop window."
        ),
        "mcp_lifecycle_policy": {
            "mode": "persistent-required",
            "one_shot_client_allowed": False,
            "reason": (
                "A short-lived Python/JVM API client may detach or exit before Desktop imports "
                "the visible main model, which can destabilize some COMSOL Server sessions."
            ),
            "required_behavior": (
                "Keep the MCP process alive after loading the main MPH and through Desktop import "
                "and visible-main iterations."
            ),
        },
        "fixed_interaction_method": [
            "User manually starts COMSOL Server.",
            "MCP must run as a persistent process, not as a one-shot Python/JVM probe.",
            "MCP checks the port.",
            "If no server is listening, MCP asks the user to create one and provide the port.",
            "If a server is listening, MCP loads and locks the main MPH.",
            "MCP tells the user to connect Desktop and import/select the current server model.",
        ],
    }


def start_visible_main_workflow(
    host: str = _srv.DEFAULT_HOST,
    port: int = _srv.DEFAULT_PORT,
    path: str = "",
) -> str:
    """Fixed visible workflow entrypoint: check port, connect, load MPH, then instruct Desktop import."""

    def _impl() -> dict[str, Any]:
        return _start_visible_main_workflow_payload(host, port, path, action="start_visible_main_workflow")

    return _run_tool("start_visible_main_workflow", _impl)


def start_visible_main_workflow_async(
    host: str = _srv.DEFAULT_HOST,
    port: int = _srv.DEFAULT_PORT,
    path: str = "",
) -> str:
    """Start visible-main loading in a background job so large MPH loads do not hit tool timeouts."""

    def _impl() -> dict[str, Any]:
        payload = {
            "host": host or _srv.DEFAULT_HOST,
            "port": int(port),
            "path": path,
        }
        job_id = _create_background_job("visible_main_workflow", payload)
        _write_workflow_state(
            {
                "last_action": "start_visible_main_workflow_async",
                "workflow_stage": "visible_main_workflow_job_started",
                "visible_main_workflow_job_id": job_id,
                "mcp_client_lifecycle": "persistent-required",
                "one_shot_client_allowed": False,
            }
        )

        def _worker() -> None:
            _update_background_job(job_id, status="running", stage="starting")
            try:
                result = _start_visible_main_workflow_payload(
                    payload["host"],
                    payload["port"],
                    payload["path"],
                    action="start_visible_main_workflow_async",
                )
            except Exception as exc:
                logging.exception("Background visible-main workflow %s failed", job_id)
                _update_background_job(job_id, status="failed", stage="failed", error=str(exc))
                _append_operation(
                    {
                        "tool": "start_visible_main_workflow_async.worker",
                        "success": False,
                        "error": str(exc),
                        "data": {"job_id": job_id, "payload": payload},
                    }
                )
                return
            _update_background_job(job_id, status="succeeded", stage="completed", result=result)
            _append_operation(
                {
                    "tool": "start_visible_main_workflow_async.worker",
                    "success": True,
                    "error": "",
                    "data": {"job_id": job_id, "result": result},
                }
            )

        thread = threading.Thread(target=_worker, name=job_id, daemon=True)
        thread.start()
        return {
            "job_id": job_id,
            "status": "running",
            "poll_tool": "visible_main_workflow_status",
            "workflow": _read_workflow_state(),
            "message": "Visible-main loading started in the persistent MCP process. Poll visible_main_workflow_status(job_id).",
        }

    return _run_tool("start_visible_main_workflow_async", _impl)


def visible_main_workflow_status(job_id: str = "") -> str:
    """Return status for the latest or specified asynchronous visible-main workflow job."""
    _setup_logging()
    job = _read_background_job(job_id)
    success = bool(job)
    return _json(
        {
            "success": success,
            "tool": "visible_main_workflow_status",
            "timestamp": __import__("time").time(),
            "datetime": _now_iso(),
            "server": _status_payload(),
            "data": {
                "job": job,
                "workflow": _read_workflow_state(),
            },
            "error": "" if success else "No visible-main workflow job found.",
            "log_path": str(SERVER_LOG),
            "operations_path": str(OPERATIONS_FILE),
        }
    )


def load_current_main_model() -> str:
    """Load the persisted current main model into the connected COMSOL server session."""

    def _impl() -> dict[str, Any]:
        client = _require_client()
        workflow = _read_workflow_state()
        if _visible_main_lock_enabled(workflow):
            payload = json.loads(load_visible_main_model(str(workflow.get("current_main_model_path", ""))))
            if not payload.get("success", False):
                raise RuntimeError(payload.get("error", "load_visible_main_model failed"))
            return payload.get("data", {})
        current_main = str(workflow.get("current_main_model_path", "") or "").strip()
        if not current_main:
            raise RuntimeError("No current main model path is configured in workflow_state.json.")
        resolved = _resolve_path(current_main)
        model = _adopt_model_by_path(str(resolved))
        origin = "workflow-main-adopted"
        if model is None:
            model = _timed_call(
                client.load, resolved,
                timeout=300.0,
                error_msg=f"Loading model {resolved} timed out after 300s.",
            )
            origin = "workflow-main-loaded"
        _set_current_model(model, origin=origin, requested_path=str(resolved))
        removed, kept = _prune_loaded_models_locked(model)
        workflow = _write_workflow_state(
            {
                "last_action": "load_current_main_model",
                "last_loaded_main_model_path": str(resolved),
                "last_loaded_at": _now_iso(),
                "last_prune_keep_mode": "main",
                "last_prune_kept_tag": _safe_model_tag(model),
                "last_prune_removed_count": len(removed),
                "last_prune_at": _now_iso(),
            }
        )
        return {
            "label": _safe_model_label(model),
            "file_path": _safe_model_path(model),
            "workflow": workflow,
            "load_mode": origin,
            "removed_loaded_models": removed,
            "remaining_loaded_models": kept,
        }

    return _run_tool("load_current_main_model", _impl)


def register(mcp_instance) -> None:
    mcp_instance.add_tool(workflow_info)
    mcp_instance.add_tool(configure_single_main_workflow)
    mcp_instance.add_tool(load_visible_main_model)
    mcp_instance.add_tool(start_visible_main_workflow)
    mcp_instance.add_tool(start_visible_main_workflow_async)
    mcp_instance.add_tool(visible_main_workflow_status)
    mcp_instance.add_tool(verify_visible_main_session)
    mcp_instance.add_tool(unlock_visible_main)
    mcp_instance.add_tool(mcp_tool_audit)
    mcp_instance.add_tool(model_tree)
    mcp_instance.add_tool(run_study)
    mcp_instance.add_tool(load_current_main_model)
