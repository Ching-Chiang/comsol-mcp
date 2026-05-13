#!/usr/bin/env python3
"""FastMCP instance, global runtime state, and configuration constants."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# Lazy mph import: defer until first use so pip installs mid-session work.
_mph: Any | None = None
_mph_import_error = ""


def _get_mph():
    """Return the mph module, importing it on first call if needed."""
    global _mph, _mph_import_error
    if _mph is not None:
        return _mph
    try:
        import mph as _m
        _mph = _m
        _mph_import_error = ""
    except Exception as exc:  # pragma: no cover - handled at runtime
        _mph_import_error = str(exc)
    return _mph


def _get_mph_error() -> str:
    """Trigger import if needed, then return any error string."""
    _get_mph()
    return _mph_import_error

VERSION = "0.1.9"
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMSOL_ROOT = Path(r"C:\Program Files\COMSOL\COMSOL63\Multiphysics")
DEFAULT_SERVER_HOME = WORKSPACE_ROOT / "comsol-server-home"

COMSOL_ROOT = Path(os.environ.get("COMSOL_ROOT", str(DEFAULT_COMSOL_ROOT))).expanduser()
COMSOL_SERVER_MCP_HOME = Path(
    os.environ.get("COMSOL_SERVER_MCP_HOME", str(DEFAULT_SERVER_HOME))
).expanduser()
DEFAULT_TIMEOUT = int(os.environ.get("COMSOL_SERVER_TIMEOUT_SECONDS", "120"))
DEFAULT_HOST = os.environ.get("COMSOL_SERVER_HOST", "localhost")
DEFAULT_PORT = int(os.environ.get("COMSOL_SERVER_PORT", "2036"))
DEFAULT_VERSION = os.environ.get("COMSOL_SERVER_VERSION", "").strip() or None

COMSOL_MPHSERVER = COMSOL_ROOT / "bin" / "win64" / "comsolmphserver.exe"
COMSOL_MPHCLIENT = COMSOL_ROOT / "bin" / "win64" / "comsolmphclient.exe"

LOGS_DIR = COMSOL_SERVER_MCP_HOME / "logs"
OUTPUTS_DIR = COMSOL_SERVER_MCP_HOME / "outputs"
STATUS_FILE = COMSOL_SERVER_MCP_HOME / "status.json"
WORKFLOW_FILE = COMSOL_SERVER_MCP_HOME / "workflow_state.json"
OPERATIONS_FILE = LOGS_DIR / "operations.jsonl"
SERVER_LOG = LOGS_DIR / "server.log"

# ---------------------------------------------------------------------------
# Global runtime state (all tool execution is guarded by _runtime_lock)
# ---------------------------------------------------------------------------
_runtime_lock = threading.RLock()
_server: Any | None = None
_client: Any | None = None
_client_connected = False
_connected_host = ""
_connected_port: int | None = None
_current_model: Any | None = None
_current_model_origin = ""
_current_model_path = ""
_server_started_by_mcp = False
_last_command = ""
_last_error = ""
_logger_ready = False
_background_jobs: dict[str, dict[str, Any]] = {}
_background_jobs_lock = threading.RLock()

# ---------------------------------------------------------------------------
# FastMCP instance (shared across all tool modules)
# ---------------------------------------------------------------------------
mcp = FastMCP("comsol-mcp-server")

RECOMMENDED_DESKTOP_FLOW = (
    "visible-main-first: manually start COMSOL Multiphysics Server, "
    "start a persistent MCP process, call start_visible_main_workflow(host, port, path); "
    "after that connect COMSOL Desktop to the same server and import the already loaded model."
)

# ---------------------------------------------------------------------------
# Tool classification sets (for visible-main guard)
# ---------------------------------------------------------------------------
SAFE_READ_TOOLS = {
    "server_info",
    "check_server_port",
    "workflow_info",
    "model_tree",
    "get_parameters",
    "evaluate_expressions",
    "get_core_metrics",
}
SAFE_VISIBLE_MAIN_WRITE_TOOLS = {
    "set_parameters",
    "ensure_component",
    "ensure_geometry",
    "ensure_mesh",
    "create_feature",
    "update_feature",
    "delete_feature",
    "run_feature",
    "run_study",
    "run_visible_main_iteration",
    "save_main_model_snapshot",
    "save_model",
}
RESTRICTED_TOOLS = {
    "commit_current_main_model",
    "model_create",
    "model_load",
    "prune_loaded_models",
}


# ---------------------------------------------------------------------------
# Basic infrastructure
# ---------------------------------------------------------------------------
def _ensure_dirs() -> None:
    for directory in (COMSOL_SERVER_MCP_HOME, LOGS_DIR, OUTPUTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _setup_logging() -> None:
    global _logger_ready
    if _logger_ready:
        return
    _ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(SERVER_LOG, encoding="utf-8"),
        ],
    )
    _logger_ready = True
