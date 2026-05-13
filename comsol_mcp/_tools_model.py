#!/usr/bin/env python3
"""MCP tools: model_create, model_load, prune_loaded_models."""

from __future__ import annotations

from typing import Any

import comsol_mcp._server as _srv
from comsol_mcp._state import (
    _run_tool, _now_iso, _resolve_path, _read_workflow_state, _write_workflow_state,
    _safe_model_label, _safe_model_path, _safe_model_tag,
)
from comsol_mcp._connection import _require_client
from comsol_mcp._model import (
    _set_current_model, _adopt_model_by_path, _block_if_visible_main_locked,
    _prune_loaded_models_locked, _require_model,
)


def model_create(name: str = "Server Model") -> str:
    """Create a new in-memory model on the connected COMSOL server and select it as current."""

    def _impl() -> dict[str, Any]:
        _block_if_visible_main_locked("model_create")
        client = _require_client()
        model = client.create(name.strip() or "Server Model")
        _set_current_model(model, origin="created")
        return {
            "label": _safe_model_label(model),
            "file_path": _safe_model_path(model),
        }

    return _run_tool("model_create", _impl)


def model_load(path: str) -> str:
    """Load an MPH file on the connected COMSOL server and select it as current."""

    def _impl() -> dict[str, Any]:
        _block_if_visible_main_locked("model_load")
        client = _require_client()
        resolved = _resolve_path(path)
        model = _adopt_model_by_path(str(resolved))
        origin = "adopted-by-path"
        if model is None:
            model = client.load(resolved)
            origin = "loaded"
        _set_current_model(model, origin=origin, requested_path=str(resolved))
        return {
            "label": _safe_model_label(model),
            "file_path": _safe_model_path(model),
            "requested_path": str(resolved),
            "load_mode": origin,
        }

    return _run_tool("model_load", _impl)


def prune_loaded_models(keep: str = "current") -> str:
    """Remove extra loaded server-side models and keep only the requested working model."""

    def _impl() -> dict[str, Any]:
        _block_if_visible_main_locked("prune_loaded_models")
        client = _require_client()
        keep_mode = str(keep or "current").strip().lower()
        keep_model = None
        workflow = _read_workflow_state()
        if keep_mode in ("current", "selected"):
            keep_model = _srv._current_model
        elif keep_mode in ("main", "workflow-main"):
            current_main = str(workflow.get("current_main_model_path", "") or "").strip()
            if current_main:
                keep_model = _adopt_model_by_path(current_main)
        else:
            raise ValueError('keep must be "current" or "main".')
        if keep_model is None:
            raise RuntimeError("No keep-model is available to preserve during prune.")

        keep_tag = _safe_model_tag(keep_model)
        removed, kept = _prune_loaded_models_locked(keep_model)
        workflow = _write_workflow_state(
            {
                "last_action": "prune_loaded_models",
                "last_prune_keep_mode": keep_mode,
                "last_prune_kept_tag": keep_tag,
                "last_prune_removed_count": len(removed),
                "last_prune_at": _now_iso(),
            }
        )
        return {
            "keep_mode": keep_mode,
            "kept": kept,
            "removed": removed,
            "removed_count": len(removed),
            "remaining_count": len(kept),
            "workflow": workflow,
        }

    return _run_tool("prune_loaded_models", _impl)


def register(mcp_instance) -> None:
    mcp_instance.add_tool(model_create)
    mcp_instance.add_tool(model_load)
    mcp_instance.add_tool(prune_loaded_models)
