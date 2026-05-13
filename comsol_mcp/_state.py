#!/usr/bin/env python3
"""Workflow state persistence, status/operations logging, path utilities, and tool infrastructure."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Any

from comsol_mcp._server import (
    COMSOL_SERVER_MCP_HOME, COMSOL_ROOT, DEFAULT_HOST,
    LOGS_DIR, OUTPUTS_DIR, STATUS_FILE, WORKFLOW_FILE, OPERATIONS_FILE, SERVER_LOG,
    _runtime_lock, _background_jobs_lock, _background_jobs,
    _client, _client_connected, _connected_host, _connected_port,
    _current_model, _current_model_origin, _current_model_path,
    _server, _server_started_by_mcp, _last_command, _last_error,
    VERSION, WORKSPACE_ROOT, RECOMMENDED_DESKTOP_FLOW,
    _ensure_dirs, _setup_logging,
    _get_mph, _get_mph_error,
)


# ---------------------------------------------------------------------------
# JSON / time helpers
# ---------------------------------------------------------------------------
def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Model label / path helpers (used by _status_payload, moved here to avoid
# pulling in _model.py which depends on this module)
# ---------------------------------------------------------------------------
def _safe_model_label(model: Any | None) -> str:
    if model is None:
        return ""
    try:
        return str(model.java.label())
    except Exception:
        try:
            return str(model.name())
        except Exception:
            return ""


def _safe_model_path(model: Any | None) -> str:
    if model is None:
        return ""
    try:
        path = str(model.java.getFilePath() or "")
    except Exception:
        path = ""
    if path:
        return str(Path(path).resolve())
    return ""


def _safe_model_tag(model: Any | None) -> str:
    if model is None:
        return ""
    try:
        return str(model.java.tag())
    except Exception:
        try:
            return str(model.name())
        except Exception:
            return ""


def _resolved_model_file_path(model: Any | None) -> str:
    path = str(_safe_model_path(model) or "").strip()
    if not path:
        return ""
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return path


def _normcase_path(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    try:
        return os.path.normcase(str(Path(raw).expanduser().resolve()))
    except Exception:
        return os.path.normcase(raw)


# ---------------------------------------------------------------------------
# Workflow state persistence
# ---------------------------------------------------------------------------
def _default_workflow_state() -> dict[str, Any]:
    return {
        "mode": "manual",
        "current_main_model_path": "",
        "snapshot_dir": "",
        "snapshot_prefix": "",
        "snapshot_name_template": "{prefix}_{label}_{timestamp}.mph",
        "visible_main_locked": False,
        "guard_level": "strict",
        "snapshot_save_mode": "copy",
        "main_model_tag": "",
        "main_model_label": "",
        "main_model_path": "",
        "workflow_stage": "awaiting_manual_server",
        "mcp_client_lifecycle": "persistent-required",
        "one_shot_client_allowed": False,
        "notes": "",
        "updated_at": _now_iso(),
    }


def _read_workflow_state() -> dict[str, Any]:
    _ensure_dirs()
    if not WORKFLOW_FILE.exists():
        state = _default_workflow_state()
        WORKFLOW_FILE.write_text(_json(state), encoding="utf-8")
        return state
    try:
        data = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    state = _default_workflow_state()
    if isinstance(data, dict):
        state.update(data)
    return state


def _write_workflow_state(update: dict[str, Any]) -> dict[str, Any]:
    state = _read_workflow_state()
    state.update(update)
    state["updated_at"] = _now_iso()
    tmp_path = WORKFLOW_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(_json(state), encoding="utf-8")
    os.replace(tmp_path, WORKFLOW_FILE)
    return state


# ---------------------------------------------------------------------------
# Status and operations logging
# ---------------------------------------------------------------------------
def _status_payload(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    connected = bool(_client_connected)
    server_running = False
    server_port = None
    if _server is not None:
        try:
            server_running = bool(_server.running())
            server_port = getattr(_server, "port", None)
        except Exception:
            server_running = False
            server_port = getattr(_server, "port", None)
    elif connected:
        server_port = _connected_port

    attached_to_existing_server = bool(connected and not _server_started_by_mcp)
    server_host = _connected_host or DEFAULT_HOST

    payload = {
        "version": VERSION,
        "timestamp": time.time(),
        "datetime": _now_iso(),
        "status": "ready" if connected else "disconnected",
        "server_running": server_running,
        "server_started_by_mcp": _server_started_by_mcp,
        "attached_to_existing_server": attached_to_existing_server,
        "server_host": server_host,
        "server_port": server_port,
        "server_endpoint": (
            f"{server_host}:{server_port}"
            if server_port
            else ""
        ),
        "desktop_client_role": "visual-client",
        "comsol_root": str(COMSOL_ROOT),
        "mcp_home": str(COMSOL_SERVER_MCP_HOME),
        "logs_dir": str(LOGS_DIR),
        "outputs_dir": str(OUTPUTS_DIR),
        "current_model_label": _safe_model_label(_current_model),
        "current_model_path": _current_model_path or _safe_model_path(_current_model),
        "current_model_origin": _current_model_origin,
        "last_command": _last_command,
        "last_error": _last_error,
        "recommended_desktop_flow": RECOMMENDED_DESKTOP_FLOW,
        "desktop_should_connect": {
            "host": server_host,
            "port": server_port,
        },
        "workflow": _read_workflow_state(),
    }
    if extra:
        payload.update(extra)
    return payload


def _write_status(extra: dict[str, Any] | None = None) -> None:
    _ensure_dirs()
    payload = _status_payload(extra)
    tmp_path = STATUS_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(_json(payload), encoding="utf-8")
    os.replace(tmp_path, STATUS_FILE)


def _append_operation(event: dict[str, Any]) -> None:
    _ensure_dirs()
    payload = {
        "timestamp": time.time(),
        "datetime": _now_iso(),
        **event,
    }
    with OPERATIONS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------------------
# Background job management
# ---------------------------------------------------------------------------
def _create_background_job(kind: str, payload: dict[str, Any]) -> str:
    job_id = f"{kind}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    with _background_jobs_lock:
        _background_jobs[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "status": "running",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "payload": payload,
            "result": {},
            "error": "",
        }
    return job_id


def _update_background_job(job_id: str, **update: Any) -> dict[str, Any]:
    with _background_jobs_lock:
        job = _background_jobs.setdefault(job_id, {"job_id": job_id})
        job.update(update)
        job["updated_at"] = _now_iso()
        return dict(job)


def _read_background_job(job_id: str = "") -> dict[str, Any]:
    with _background_jobs_lock:
        if job_id:
            return dict(_background_jobs.get(job_id, {}))
        if not _background_jobs:
            return {}
        latest_id = max(
            _background_jobs,
            key=lambda key: str(_background_jobs[key].get("updated_at", "")),
        )
        return dict(_background_jobs[latest_id])


# ---------------------------------------------------------------------------
# Path and port utilities
# ---------------------------------------------------------------------------
def _resolve_path(value: str, *, base: Path = WORKSPACE_ROOT, must_exist: bool = True) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Path is required.")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if must_exist and not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    return path


def _port_is_open(host: str, port: int, timeout_seconds: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _server_missing_guidance(host: str, port: int) -> dict[str, Any]:
    return {
        "server_available": False,
        "host": host,
        "port": int(port),
        "message": (
            f"No COMSOL Multiphysics Server is listening at {host}:{int(port)}. "
            "Please start COMSOL Multiphysics Server manually, confirm its actual port, "
            "then tell MCP that port."
        ),
        "next_step_for_user": "Start COMSOL Server manually and provide the actual listening port.",
        "mcp_policy": "MCP will not start the server in visible-main mode.",
    }


def _mark_awaiting_manual_server(host: str, port: int, action: str) -> dict[str, Any]:
    return _write_workflow_state(
        {
            "last_action": action,
            "last_checked_host": host,
            "last_checked_port": int(port),
            "last_checked_at": _now_iso(),
            "workflow_stage": "awaiting_manual_server",
            "visible_main_locked": False,
            "main_model_tag": "",
            "main_model_label": "",
            "main_model_path": "",
        }
    )


def _resolve_output_path(value: str, default_path: Path) -> Path:
    raw = str(value or "").strip()
    if not raw:
        path = default_path
    else:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = WORKSPACE_ROOT / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
def _require_mph() -> None:
    mph = _get_mph()
    if mph is None:
        raise RuntimeError(
            "MPh is not available in the MCP Python environment. "
            f"Import error: {_get_mph_error()}"
        )


def _friendly_connection_error(exc: Exception, host: str, port: int) -> RuntimeError:
    message = str(exc).strip()
    lowered = message.lower()
    endpoint = f"{host}:{port}"
    if "actively refused" in lowered or "connection refused" in lowered or "refused" in lowered:
        return RuntimeError(
            f"Connection refused for {endpoint}. The target port does not have a live "
            "COMSOL Multiphysics Server listening on it. Start the server manually and "
            "confirm the port in its console window before calling server_connect()."
        )
    if (
        "auth" in lowered
        or "password" in lowered
        or "username" in lowered
        or "login" in lowered
        or "credential" in lowered
    ):
        return RuntimeError(
            f"Authentication failed for {endpoint}. Verify the COMSOL Multiphysics "
            "Server username and password you entered when the server started."
        )
    return RuntimeError(f"Failed to connect to {endpoint}: {message or type(exc).__name__}")


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------
def _sanitize_snapshot_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (value or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned or "snapshot"


def _workflow_snapshot_path(label: str, workflow: dict[str, Any] | None = None) -> Path:
    state = workflow or _read_workflow_state()
    snapshot_dir = str(state.get("snapshot_dir", "") or "").strip()
    current_main = str(state.get("current_main_model_path", "") or "").strip()
    prefix = str(state.get("snapshot_prefix", "") or "").strip()
    template = str(state.get("snapshot_name_template", "") or "").strip() or "{prefix}_{label}_{timestamp}.mph"

    if snapshot_dir:
        base_dir = _resolve_output_path(snapshot_dir, OUTPUTS_DIR).resolve()
    elif current_main:
        base_dir = Path(current_main).expanduser().resolve().parent
    else:
        base_dir = OUTPUTS_DIR.resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    if not prefix:
        if current_main:
            prefix = Path(current_main).stem
        else:
            prefix = "server_model"
    filename = template.format(
        prefix=prefix,
        label=_sanitize_snapshot_label(label),
        timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    if not filename.lower().endswith(".mph"):
        filename += ".mph"
    return (base_dir / filename).resolve()


# ---------------------------------------------------------------------------
# Tool result / run_tool (used by every MCP tool function)
# ---------------------------------------------------------------------------
def _tool_result(tool: str, success: bool, data: dict[str, Any] | None = None, error: str = "") -> str:
    from comsol_mcp._server import _last_command, _last_error  # noqa: F811
    import comsol_mcp._server as _srv
    _srv._last_command = tool
    _srv._last_error = error
    payload = {
        "success": success,
        "tool": tool,
        "timestamp": time.time(),
        "datetime": _now_iso(),
        "server": _status_payload(),
        "data": data or {},
        "error": error,
        "log_path": str(SERVER_LOG),
        "operations_path": str(OPERATIONS_FILE),
    }
    _append_operation(
        {
            "tool": tool,
            "success": success,
            "error": error,
            "data": data or {},
        }
    )
    _write_status({"last_command": tool, "last_error": error})
    return _json(payload)


def _run_tool(tool: str, callback) -> str:
    _setup_logging()
    with _runtime_lock:
        try:
            data = callback()
            return _tool_result(tool, True, data=data)
        except Exception as exc:
            logging.exception("Tool %s failed", tool)
            return _tool_result(tool, False, error=str(exc))
