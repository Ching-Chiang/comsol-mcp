#!/usr/bin/env python3
"""Model management: adopt, prune, set current, visible-main lock mechanism."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import comsol_mcp._server as _srv
from comsol_mcp._state import (
    _json, _now_iso, _read_workflow_state, _write_workflow_state,
    _append_operation, _safe_model_label, _safe_model_path,
    _safe_model_tag, _resolved_model_file_path, _normcase_path,
    _resolve_path, _resolve_output_path, OUTPUTS_DIR,
)
from comsol_mcp._connection import _require_client


def _set_current_model(model: Any | None, *, origin: str = "", requested_path: str = "") -> None:
    _srv._current_model = model
    _srv._current_model_origin = origin
    _srv._current_model_path = requested_path or _safe_model_path(model)


def _visible_main_identity(model: Any | None = None) -> dict[str, str]:
    candidate = model if model is not None else _srv._current_model
    return {
        "tag": _safe_model_tag(candidate),
        "label": _safe_model_label(candidate),
        "path": _resolved_model_file_path(candidate),
    }


def _visible_main_lock_enabled(workflow: dict[str, Any] | None = None) -> bool:
    state = workflow if workflow is not None else _read_workflow_state()
    return bool(state.get("visible_main_locked")) and str(state.get("guard_level", "strict")).lower() == "strict"


def _visible_main_mismatch(model: Any, workflow: dict[str, Any] | None = None) -> list[str]:
    state = workflow if workflow is not None else _read_workflow_state()
    identity = _visible_main_identity(model)
    expected_tag = str(state.get("main_model_tag", "") or "").strip()
    expected_label = str(state.get("main_model_label", "") or "").strip()
    expected_path = str(state.get("main_model_path", "") or state.get("current_main_model_path", "") or "").strip()
    mismatches = []
    if expected_tag and identity["tag"] != expected_tag:
        mismatches.append(f"tag expected {expected_tag}, got {identity['tag']}")
    if expected_label and identity["label"] != expected_label:
        mismatches.append(f"label expected {expected_label}, got {identity['label']}")
    if expected_path and _normcase_path(identity["path"]) != _normcase_path(expected_path):
        mismatches.append(f"path expected {expected_path}, got {identity['path']}")
    return mismatches


def _require_visible_main(tool_name: str = "") -> Any:
    model = _require_model()
    workflow = _read_workflow_state()
    if not _visible_main_lock_enabled(workflow):
        return model
    mismatches = _visible_main_mismatch(model, workflow)
    if mismatches:
        message = (
            "Visible main model lock mismatch. "
            "Use load_visible_main_model() to reselect the locked main model. "
            + "; ".join(mismatches)
        )
        _append_operation(
            {
                "event": "visible_main_guard_blocked",
                "tool": tool_name,
                "mismatches": mismatches,
                "current": _visible_main_identity(model),
                "workflow": workflow,
            }
        )
        raise RuntimeError(message)
    return model


def _block_if_visible_main_locked(tool_name: str) -> None:
    workflow = _read_workflow_state()
    if not _visible_main_lock_enabled(workflow):
        return
    message = (
        f'{tool_name} is restricted while visible_main_locked=true and guard_level=strict. '
        "Use the visible-main workflow tools or unlock_visible_main(reason) for maintenance."
    )
    _append_operation(
        {
            "event": "visible_main_restricted_tool_blocked",
            "tool": tool_name,
            "workflow": workflow,
            "current": _visible_main_identity(_srv._current_model),
        }
    )
    raise RuntimeError(message)


def _save_model_copy(model: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    model.java.save(str(path), True)


def _adopt_model_by_name(model_name: str = "") -> Any | None:
    if _srv._client is None:
        return None
    models = list(_srv._client.models())
    if not models:
        return None
    if model_name:
        for model in models:
            if _safe_model_label(model) == model_name or model.name() == model_name:
                return model
        raise ValueError(f'Model "{model_name}" is not loaded on the connected server.')
    if len(models) == 1:
        return models[0]
    return None


def _adopt_model_by_path(path: str) -> Any | None:
    if _srv._client is None:
        return None
    target = str(path or "").strip()
    if not target:
        return None
    try:
        normalized_target = str(Path(target).expanduser().resolve())
    except Exception:
        normalized_target = target
    for model in list(_srv._client.models()):
        existing = _resolved_model_file_path(model)
        if existing and os.path.normcase(existing) == os.path.normcase(normalized_target):
            return model
    return None


def _loaded_model_records_locked() -> list[dict[str, str]]:
    client = _require_client()
    records = []
    for model in list(client.models()):
        records.append(
            {
                "tag": _safe_model_tag(model),
                "label": _safe_model_label(model),
                "file_path": _resolved_model_file_path(model),
            }
        )
    return records


def _prune_loaded_models_locked(keep_model: Any) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    client = _require_client()
    keep_tag = _safe_model_tag(keep_model)
    removed = []
    removed_tags = set()

    for _ in range(3):
        extras = []
        for model in list(client.models()):
            tag = _safe_model_tag(model)
            record = {
                "tag": tag,
                "label": _safe_model_label(model),
                "file_path": _resolved_model_file_path(model),
            }
            if tag == keep_tag:
                continue
            extras.append((model, record))
        if not extras:
            break

        progress = False
        for model, record in extras:
            tag = record["tag"]
            try:
                client.remove(model)
                progress = True
            except Exception:
                try:
                    if tag:
                        client.java.remove(tag)
                        progress = True
                except Exception:
                    logging.debug("Failed to remove loaded model tag=%s label=%s", tag, record["label"], exc_info=True)
            if tag not in removed_tags:
                removed.append(record)
                removed_tags.add(tag)
        if not progress:
            break

    kept = []
    for record in _loaded_model_records_locked():
        if record["tag"] == keep_tag:
            kept.append(record)
    _set_current_model(keep_model, origin="pruned-kept", requested_path=_resolved_model_file_path(keep_model))
    return removed, kept


def _remove_loaded_models_by_path_locked(path: str, keep_model: Any | None = None) -> list[dict[str, str]]:
    client = _require_client()
    target = str(path or "").strip()
    if not target:
        return []
    try:
        normalized_target = os.path.normcase(str(Path(target).expanduser().resolve()))
    except Exception:
        normalized_target = os.path.normcase(target)
    keep_tag = _safe_model_tag(keep_model)
    removed = []
    for model in list(client.models()):
        model_tag = _safe_model_tag(model)
        if keep_tag and model_tag == keep_tag:
            continue
        resolved = _resolved_model_file_path(model)
        if resolved and os.path.normcase(resolved) == normalized_target:
            removed.append(
                {
                    "tag": model_tag,
                    "label": _safe_model_label(model),
                    "file_path": resolved,
                }
            )
            client.remove(model)
    return removed


def _require_model() -> Any:
    _require_client()
    if _srv._current_model is None:
        adopted = _adopt_model_by_name("")
        if adopted is not None:
            _set_current_model(adopted, origin="adopted")
        else:
            raise RuntimeError(
                "No current model is selected. Use model_create() or model_load(), "
                "or connect to a server with exactly one loaded model."
            )
    return _srv._current_model


def _save_model_path(model: Any, path: str = "") -> Path:
    current_path = _safe_model_path(model)
    if path:
        target = _resolve_output_path(path, OUTPUTS_DIR / f"{_safe_model_label(model) or 'model'}.mph")
    elif current_path:
        target = Path(current_path)
    else:
        stem = _safe_model_label(model) or "server_model"
        target = _resolve_output_path("", OUTPUTS_DIR / f"{stem}.mph")
    model.save(target)
    _set_current_model(model, origin=_srv._current_model_origin or "saved", requested_path=str(target))
    return target
