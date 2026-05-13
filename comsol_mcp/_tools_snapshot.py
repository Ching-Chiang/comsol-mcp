#!/usr/bin/env python3
"""MCP tools: run_visible_main_iteration, save_main_model_snapshot, commit_current_main_model, save_model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import comsol_mcp._server as _srv
from comsol_mcp._state import (
    _run_tool, _now_iso, _resolve_output_path, OUTPUTS_DIR,
    _read_workflow_state, _write_workflow_state, _append_operation,
    _sanitize_snapshot_label, _workflow_snapshot_path,
    _safe_model_label, _safe_model_path, _safe_model_tag,
)
from comsol_mcp._connection import _require_client
from comsol_mcp._model import (
    _require_visible_main, _block_if_visible_main_locked,
    _visible_main_identity, _visible_main_mismatch, _visible_main_lock_enabled,
    _set_current_model, _save_model_copy, _remove_loaded_models_by_path_locked,
    _prune_loaded_models_locked,
)


def run_visible_main_iteration(label: str, parameters_json: str = "[]", study_tag: str = "") -> str:
    """Run one locked visible-main iteration: set parameters, solve, extract metrics, save a copy snapshot."""

    def _impl() -> dict[str, Any]:
        from comsol_mcp._tools_params import get_core_metrics

        model = _require_visible_main("run_visible_main_iteration")
        before = _visible_main_identity(model)
        parsed = json.loads(parameters_json or "[]")
        if not isinstance(parsed, list):
            raise ValueError("parameters_json must be a JSON array.")

        updated = []
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError("Each parameter entry must be an object.")
            name = str(item.get("name", "")).strip()
            expression = str(item.get("expression", "")).strip()
            if not name:
                raise ValueError("Parameter name is required.")
            model.java.param().set(name, expression)
            updated.append({"name": name, "expression": expression})

        study = str(study_tag or "").strip()
        if study:
            try:
                study_label = str(model.java.study().get(study).label())
                model.solve(study_label)
            except Exception:
                model.solve(study)
        else:
            model.solve()

        metrics_payload = json.loads(get_core_metrics())
        if not metrics_payload.get("success", False):
            raise RuntimeError(metrics_payload.get("error", "get_core_metrics failed"))
        snapshot_payload = json.loads(save_main_model_snapshot(label))
        if not snapshot_payload.get("success", False):
            raise RuntimeError(snapshot_payload.get("error", "save_main_model_snapshot failed"))
        after = _visible_main_identity(model)
        mismatches = _visible_main_mismatch(model)
        if before["tag"] != after["tag"] or before["path"] != after["path"] or mismatches:
            raise RuntimeError(
                "Visible main identity changed during iteration: "
                f"before={before}; after={after}; mismatches={mismatches}"
            )
        _append_operation(
            {
                "event": "visible_main_iteration_completed",
                "label": _sanitize_snapshot_label(label),
                "parameters": updated,
                "study_tag": study,
                "snapshot_path": snapshot_payload.get("data", {}).get("snapshot_path", ""),
                "identity": after,
            }
        )
        return {
            "label": _sanitize_snapshot_label(label),
            "parameters": updated,
            "study_tag": study,
            "metrics": metrics_payload.get("data", {}),
            "snapshot": snapshot_payload.get("data", {}),
            "identity_before": before,
            "identity_after": after,
        }

    return _run_tool("run_visible_main_iteration", _impl)


def save_main_model_snapshot(snapshot_label: str) -> str:
    """Save a named snapshot from the current server-side model using the persisted workflow naming policy."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("save_main_model_snapshot")
        workflow = _read_workflow_state()
        sanitized_label = _sanitize_snapshot_label(snapshot_label)
        snapshot_path = _workflow_snapshot_path(sanitized_label, workflow)
        before = _visible_main_identity(model)
        _save_model_copy(model, snapshot_path)
        after = _visible_main_identity(model)
        mismatches = _visible_main_mismatch(model, workflow)
        if before != after:
            mismatches.append(f"identity changed after snapshot: before={before}, after={after}")
        if mismatches:
            raise RuntimeError("Snapshot save changed visible main identity: " + "; ".join(mismatches))
        workflow = _write_workflow_state(
            {
                "last_action": "save_main_model_snapshot",
                "last_snapshot_label": sanitized_label,
                "last_snapshot_path": str(snapshot_path),
                "last_snapshot_at": _now_iso(),
                "snapshot_save_mode": "copy",
                "last_snapshot_identity_after": after,
            }
        )
        return {
            "snapshot_label": sanitized_label,
            "snapshot_path": str(snapshot_path),
            "snapshot_save_mode": "copy",
            "identity_before": before,
            "identity_after": after,
            "workflow": workflow,
        }

    return _run_tool("save_main_model_snapshot", _impl)


def commit_current_main_model(snapshot_label: str = "") -> str:
    """Save a named snapshot, then overwrite the persisted current main model with the current server-side state."""

    def _impl() -> dict[str, Any]:
        _block_if_visible_main_locked("commit_current_main_model")
        model = _require_visible_main("commit_current_main_model")
        client = _require_client()
        workflow = _read_workflow_state()
        current_main = str(workflow.get("current_main_model_path", "") or "").strip()
        if not current_main:
            raise RuntimeError("No current main model path is configured in workflow_state.json.")
        resolved_main = _resolve_output_path(current_main, OUTPUTS_DIR / "current_main_model.mph")
        resolved_main_label = Path(resolved_main).name
        label = _sanitize_snapshot_label(snapshot_label.strip() or "update")
        snapshot_path = _workflow_snapshot_path(label, workflow)
        _save_model_copy(model, snapshot_path)
        removed_conflicts = _remove_loaded_models_by_path_locked(str(resolved_main), keep_model=model)
        model.java.label(resolved_main_label)
        model.save()
        removed_after_commit, kept_after_commit = _prune_loaded_models_locked(model)
        _set_current_model(model, origin="workflow-main-committed", requested_path=str(resolved_main))
        identity = _visible_main_identity(model)
        workflow = _write_workflow_state(
            {
                "last_action": "commit_current_main_model",
                "last_snapshot_label": label,
                "last_snapshot_path": str(snapshot_path),
                "last_snapshot_at": _now_iso(),
                "snapshot_save_mode": "copy",
                "last_commit_label": label,
                "last_commit_at": _now_iso(),
                "last_committed_current_main_model_path": str(resolved_main),
                "last_committed_current_main_model_label": resolved_main_label,
                "last_commit_removed_conflict_count": len(removed_conflicts),
                "visible_main_locked": True,
                "guard_level": "strict",
                "main_model_tag": identity["tag"],
                "main_model_label": identity["label"],
                "main_model_path": identity["path"] or str(resolved_main),
                "workflow_stage": "visible_main_locked",
                "last_prune_keep_mode": "current",
                "last_prune_kept_tag": _safe_model_tag(model),
                "last_prune_removed_count": len(removed_after_commit),
                "last_prune_at": _now_iso(),
            }
        )
        return {
            "snapshot_label": label,
            "snapshot_path": str(snapshot_path),
            "current_main_model_path": str(resolved_main),
            "current_main_model_label": resolved_main_label,
            "current_main_identity": identity,
            "removed_conflicts": removed_conflicts,
            "remaining_loaded_models": kept_after_commit,
            "workflow": workflow,
        }

    return _run_tool("commit_current_main_model", _impl)


def save_model(path: str = "") -> str:
    """Save the current server-side model to disk."""

    def _impl() -> dict[str, Any]:
        from comsol_mcp._model import _save_model_path

        model = _require_visible_main("save_model")
        if str(path or "").strip() and _visible_main_lock_enabled():
            _block_if_visible_main_locked("save_model(path)")
        target = _save_model_path(model, path)
        return {
            "label": _safe_model_label(model),
            "saved_path": str(target),
        }

    return _run_tool("save_model", _impl)


def register(mcp_instance) -> None:
    mcp_instance.add_tool(run_visible_main_iteration)
    mcp_instance.add_tool(save_main_model_snapshot)
    mcp_instance.add_tool(commit_current_main_model)
    mcp_instance.add_tool(save_model)
