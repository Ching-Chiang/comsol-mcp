#!/usr/bin/env python3
"""Pure helpers for solver configuration operations (no global state)."""

from __future__ import annotations

from typing import Any

from comsol_mcp._model_ops import _normalize_properties, _apply_feature_properties


# ---------------------------------------------------------------------------
# Solver configuration helpers
# ---------------------------------------------------------------------------
def _list_solver_configs(model: Any) -> list[dict[str, Any]]:
    java = model.java
    tags = list(java.sol().tags())
    result = []
    for tag in tags:
        sol = java.sol(tag)
        info: dict[str, Any] = {"tag": tag}
        try:
            features = list(sol.feature().tags())
            info["features"] = features
            info["feature_count"] = len(features)
        except Exception:
            info["features"] = []
            info["feature_count"] = 0
        result.append(info)
    return result


def _list_solver_features(model: Any, sol_tag: str) -> list[dict[str, Any]]:
    sol = model.java.sol(sol_tag)
    tags = list(sol.feature().tags())
    result = []
    for tag in tags:
        feat = sol.feature(tag)
        info: dict[str, Any] = {"tag": tag}
        try:
            info["label"] = str(feat.label())
        except Exception:
            pass
        try:
            props = list(feat.properties())
            info["properties"] = props
        except Exception:
            info["properties"] = []
        # Check for sub-features (e.g., segregated solver steps)
        try:
            sub_tags = list(feat.feature().tags())
            if sub_tags:
                info["sub_features"] = sub_tags
                info["sub_feature_count"] = len(sub_tags)
        except Exception:
            pass
        result.append(info)
    return result


def _create_solver_config(model: Any, sol_tag: str, study_tag: str) -> dict[str, Any]:
    java = model.java
    existing = list(java.sol().tags())
    if sol_tag in existing:
        return {"sol_tag": sol_tag, "study_tag": study_tag, "created": False, "message": "Solver config already exists."}
    java.sol().create(sol_tag, study_tag)
    return {"sol_tag": sol_tag, "study_tag": study_tag, "created": True}


def _configure_solver_feature(
    model: Any, sol_tag: str, feature_tag: str,
    properties_json: str,
) -> list[dict[str, Any]]:
    feat = model.java.sol(sol_tag).feature(feature_tag)
    props = _normalize_properties(properties_json)
    return _apply_feature_properties(feat, props)


def _list_segregated_steps(model: Any, sol_tag: str, seg_tag: str) -> list[dict[str, Any]]:
    seg = model.java.sol(sol_tag).feature(seg_tag)
    tags = list(seg.feature().tags())
    result = []
    for tag in tags:
        step = seg.feature(tag)
        info: dict[str, Any] = {"tag": tag}
        try:
            info["label"] = str(step.label())
        except Exception:
            pass
        try:
            segvar = step.getString("segvar")
            info["variables"] = list(segvar) if segvar else []
        except Exception:
            info["variables"] = []
        result.append(info)
    return result


def _add_segregated_step(
    model: Any, sol_tag: str, seg_tag: str, step_tag: str, variables: list[str],
) -> dict[str, Any]:
    seg = model.java.sol(sol_tag).feature(seg_tag)
    existing = list(seg.feature().tags())
    if step_tag in existing:
        return {"step_tag": step_tag, "created": False, "message": "Segregated step already exists."}
    seg.feature().create(step_tag, "SegStep")
    step = seg.feature(step_tag)
    if variables:
        step.set("segvar", variables)
    return {"step_tag": step_tag, "variables": variables, "created": True}
