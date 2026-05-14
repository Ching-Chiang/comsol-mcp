#!/usr/bin/env python3
"""Pure model operation helpers: parameters, expressions, metrics, tree, geometry."""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Parameter helpers
# ---------------------------------------------------------------------------
def _parameter_rows(model: Any) -> list[dict[str, str]]:
    names = list(model.java.param().varnames())
    rows = []
    for name in names:
        key = str(name)
        rows.append(
            {
                "name": key,
                "expression": str(model.java.param().get(key)),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Expression evaluation helpers
# ---------------------------------------------------------------------------
def _coerce_eval_value(value: Any) -> Any:
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_coerce_eval_value(item) for item in value]
    return str(value)


def _last_scalar(value: Any) -> Any:
    current = value
    while isinstance(current, list) and current:
        current = current[-1]
    return current


def _evaluate_named_expressions(model: Any, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each expression entry must be an object.")
        name = str(item.get("name", "")).strip()
        expression = str(item.get("expression", "")).strip()
        if not name:
            raise ValueError("Expression name is required.")
        if not expression:
            raise ValueError(f'Expression is required for "{name}".')
        row: dict[str, Any] = {"name": name, "expression": expression}
        try:
            raw = model.evaluate(expression)
            value = _coerce_eval_value(raw)
            row["value"] = value
            row["last_value"] = _coerce_eval_value(_last_scalar(value))
            row["ok"] = True
        except Exception as exc:
            row["ok"] = False
            row["error"] = str(exc)
        results.append(row)
    return results


def _clear_numerical(model: Any) -> None:
    numerical = model.java.result().numerical()
    for tag in list(numerical.tags()):
        numerical.remove(str(tag))


def _numeric_result(name: str, expression: str, value: Any = None, *, ok: bool = True, error: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "expression": expression, "ok": ok}
    if ok:
        row["value"] = value
        row["last_value"] = _coerce_eval_value(_last_scalar(value))
    else:
        row["error"] = error or "NA"
    return row


# ---------------------------------------------------------------------------
# Core metrics helpers
# ---------------------------------------------------------------------------
def _find_initialized_solution_tag(model: Any) -> str:
    for tag in list(model.java.sol().tags()):
        tag_str = str(tag)
        try:
            if model.java.sol(tag_str).isInitialized():
                return tag_str
        except Exception:
            continue
    return ""


def _read_last_time_day(model: Any, sol_tag: str) -> float | None:
    if not sol_tag:
        return None
    try:
        values = model.java.sol(sol_tag).getPVals()
        if values is not None and len(values) > 0:
            last_value = float(values[-1])
            return last_value / 86400.0 if abs(last_value) > 1e3 else last_value
    except Exception:
        return None
    return None


def _eval_global_last(model: Any, expression: str) -> float | None:
    try:
        _clear_numerical(model)
        numerical_list = model.java.result().numerical()
        numerical_list.create("gev1", "EvalGlobal")
        feature = model.java.result().numerical("gev1")
        feature.set("expr", [expression])
        feature.setIndex("looplevelinput", "last", 0)
        feature.run()
        return float(feature.getReal()[0][0])
    except Exception:
        return None


def _eval_domain_average_last(model: Any, expression: str, domains: list[int]) -> float | None:
    try:
        _clear_numerical(model)
        numerical_list = model.java.result().numerical()
        numerical_list.create("dom1", "IntSurface")
        feature = model.java.result().numerical("dom1")
        feature.selection().geom("geom1", 2)
        feature.selection().set(domains)
        feature.set("intvolume", True)
        feature.set("expr", [expression, "1"])
        feature.setIndex("looplevelinput", "last", 0)
        feature.run()
        values = feature.getReal()
        return float(values[0][0] / values[1][0])
    except Exception:
        return None


def _eval_boundary_average_last(model: Any, expression: str, boundaries: list[int]) -> float | None:
    try:
        _clear_numerical(model)
        numerical_list = model.java.result().numerical()
        numerical_list.create("int1", "IntLine")
        feature = model.java.result().numerical("int1")
        feature.selection().geom("geom1", 1)
        feature.selection().set(boundaries)
        feature.set("intsurface", True)
        feature.set("expr", [expression, "1"])
        feature.setIndex("looplevelinput", "last", 0)
        feature.run()
        values = feature.getReal()
        return float(values[0][0] / values[1][0])
    except Exception:
        return None


def _eval_extremum_last(model: Any, feature_type: str, expression: str, domains: list[int]) -> float | None:
    try:
        _clear_numerical(model)
        numerical_list = model.java.result().numerical()
        numerical_list.create("ext1", feature_type)
        feature = model.java.result().numerical("ext1")
        feature.selection().geom("geom1", 2)
        feature.selection().set(domains)
        feature.set("expr", [expression])
        feature.setIndex("looplevelinput", "last", 0)
        feature.run()
        return float(feature.getReal()[0][0])
    except Exception:
        return None


def _get_model_dimension(model: Any) -> int:
    """Get the configured or auto-detected spatial dimension of the model.

    Priority:
    1. Workflow state `model_dimension` (set by configure_single_main_workflow)
    2. Auto-detect from existing physics interfaces
    3. Default to 0 (unknown)
    """
    # Check workflow state first
    try:
        from comsol_mcp._state import _read_workflow_state
        state = _read_workflow_state()
        dim = int(state.get("model_dimension", 0))
        if dim in (1, 2, 3):
            return dim
    except Exception:
        pass

    # Auto-detect from existing physics interfaces
    try:
        comps = list(model.java.component().tags())
        if comps:
            comp = model.java.component(comps[0])
            phys_tags = list(comp.physics().tags())
            if phys_tags:
                phys = comp.physics(phys_tags[0])
                # Try common API methods for getting spatial dimension from physics
                for method_name in ("getNDim", "getSpatialDim", "sdim", "getDim"):
                    try:
                        val = getattr(phys, method_name)
                        if callable(val):
                            d = int(val())
                            if d in (1, 2, 3):
                                return d
                        else:
                            d = int(val)
                            if d in (1, 2, 3):
                                return d
                    except Exception:
                        continue
                # Try reading the physics selection dimension
                try:
                    sel = phys.feature().tags()
                    if sel:
                        feat = phys.feature(sel[0])
                        # The selection geom dimension reveals spatial dim
                        for attr_name in ("_geomDim", "dim"):
                            try:
                                d = int(getattr(feat.selection(), attr_name))
                                if d in (1, 2, 3):
                                    return d
                            except Exception:
                                continue
                except Exception:
                    pass
    except Exception:
        pass

    return 0


def _evaluate_aggregate(
    model: Any,
    expression: str,
    aggregate: str,
    domains: list[int] | None = None,
    boundaries: list[int] | None = None,
    time_point: str = "last",
) -> Any:
    """Evaluate an expression with aggregation. Returns scalar for aggregated, raw for 'none'.

    Automatically selects correct COMSOL result feature type based on model dimension:
    - 3D: domains→Volume, boundaries→Surface
    - 2D: domains→Surface, boundaries→Line
    - 1D: domains→Line, boundaries→Point
    """
    aggregate = (aggregate or "none").lower().strip()
    if aggregate == "none":
        raw = model.evaluate(expression)
        return _coerce_eval_value(raw)

    _clear_numerical(model)
    numerical_list = model.java.result().numerical()

    # Get spatial dimension from workflow config or auto-detect
    dim = _get_model_dimension(model)
    if dim == 0:
        dim = 2  # Default to 2D if unknown (common for structural mechanics)

    # Map: (dim, entity) → suffix for max/min/int
    # 3D: domains=Volume, boundaries=Surface
    # 2D: domains=Surface, boundaries=Line
    # 1D: domains=Line, boundaries=Point (rare)
    if boundaries:
        geom_dim = max(dim - 1, 1)  # boundary is (dim-1) entity
    elif domains:
        geom_dim = dim
    else:
        geom_dim = dim

    dim_suffix = {3: "Volume", 2: "Surface", 1: "Line"}.get(geom_dim, "Surface")

    # Choose correct COMSOL result feature type
    if aggregate == "max":
        if domains or boundaries:
            tag, ftype = "agg1", f"Max{dim_suffix}"
        else:
            tag, ftype = "agg1", f"Max{dim_suffix}"
    elif aggregate == "min":
        if domains or boundaries:
            tag, ftype = "agg1", f"Min{dim_suffix}"
        else:
            tag, ftype = "agg1", f"Min{dim_suffix}"
    elif aggregate == "avg":
        if domains or boundaries:
            tag, ftype = "agg1", f"Int{dim_suffix}"
        else:
            tag, ftype = "agg1", "EvalGlobal"
    elif aggregate == "integral":
        tag, ftype = "agg1", f"Int{dim_suffix}"
    else:
        raise ValueError(f'Unknown aggregate "{aggregate}". Use max, min, avg, integral, or none.')

    numerical_list.create(tag, ftype)
    feature = model.java.result().numerical(tag)

    # Set selection with correct geometric dimension
    if domains:
        feature.selection().geom("geom1", dim)
        feature.selection().set(domains)
    elif boundaries:
        feature.selection().geom("geom1", max(dim - 1, 1))
        feature.selection().set(boundaries)

    # Set expression(s) based on aggregate type
    if aggregate == "avg" and (domains or boundaries):
        feature.set("expr", [expression, "1"])
    else:
        feature.set("expr", [expression])

    if time_point and time_point != "all":
        feature.setIndex("looplevelinput", time_point, 0)

    feature.run()
    values = feature.getReal()

    if aggregate == "avg" and (domains or boundaries):
        denom = values[1][0]
        if denom == 0:
            return float("nan")
        return float(values[0][0] / denom)
    return float(values[0][0])


# ---------------------------------------------------------------------------
# Model tree
# ---------------------------------------------------------------------------
def _model_tree_data(model: Any) -> dict[str, Any]:
    from comsol_mcp._state import _safe_model_label, _safe_model_path
    java = model.java
    components = [str(tag) for tag in java.component().tags()]
    component_details = []
    for component in components:
        comp = java.component(component)
        component_details.append(
            {
                "tag": component,
                "geometries": [str(tag) for tag in comp.geom().tags()],
                "meshes": [str(tag) for tag in comp.mesh().tags()],
                "physics": [str(tag) for tag in comp.physics().tags()],
                "materials": [str(tag) for tag in comp.material().tags()],
            }
        )
    return {
        "label": _safe_model_label(model),
        "file_path": _safe_model_path(model),
        "components": components,
        "component_details": component_details,
        "parameters": [row["name"] for row in _parameter_rows(model)],
        "studies": [str(tag) for tag in java.study().tags()],
        "solutions": [str(tag) for tag in java.sol().tags()],
        "datasets": [str(tag) for tag in java.result().dataset().tags()],
        "results": [str(tag) for tag in java.result().tags()],
    }


# ---------------------------------------------------------------------------
# Geometry feature helpers
# ---------------------------------------------------------------------------
def _normalize_properties(properties_json: str) -> list[tuple[str, list[str]]]:
    raw = str(properties_json or "").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    items: list[dict[str, Any]]
    if isinstance(parsed, dict):
        items = []
        for name, value in parsed.items():
            if isinstance(value, list):
                items.append({"name": name, "values": [str(item) for item in value]})
            else:
                items.append({"name": name, "value": str(value)})
    elif isinstance(parsed, list):
        items = parsed
    else:
        raise ValueError("properties_json must be a JSON object or array.")

    normalized: list[tuple[str, list[str]]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each properties_json entry must be an object.")
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        if "values" in item:
            values = item.get("values")
            if not isinstance(values, list):
                raise ValueError(f'Property "{name}" values must be an array.')
            normalized.append((name, [str(value) for value in values]))
        elif "value" in item:
            normalized.append((name, [str(item.get("value", ""))]))
        else:
            raise ValueError(f'Property "{name}" must include value or values.')
    return normalized


def _ensure_component_java(model: Any, component: str, dimension: int) -> dict[str, Any]:
    java = model.java
    if component not in list(java.component().tags()):
        java.component().create(component, True)
    return {"component": component, "dimension": dimension}


def _ensure_geometry_java(model: Any, component: str, geometry: str, dimension: int) -> dict[str, Any]:
    java = model.java
    if component not in list(java.component().tags()):
        java.component().create(component, True)
    if dimension <= 0:
        dimension = 2
    if geometry not in list(java.component(component).geom().tags()):
        java.component(component).geom().create(geometry, dimension)
    return {"component": component, "geometry": geometry, "dimension": dimension}


def _ensure_mesh_java(model: Any, component: str, mesh: str) -> dict[str, Any]:
    java = model.java
    if component not in list(java.component().tags()):
        java.component().create(component, True)
    if mesh not in list(java.component(component).mesh().tags()):
        java.component(component).mesh().create(mesh)
    return {"component": component, "mesh": mesh}


def _apply_feature_properties(feature: Any, properties: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    applied = []
    for name, values in properties:
        if len(values) <= 1:
            feature.set(name, values[0] if values else "")
            applied.append({"name": name, "value": values[0] if values else ""})
        else:
            feature.set(name, values)
            applied.append({"name": name, "values": values})
    return applied
