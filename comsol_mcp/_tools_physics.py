#!/usr/bin/env python3
"""MCP tools: physics interface management and variable definitions."""

from __future__ import annotations

import json
from typing import Any

from comsol_mcp._state import _run_tool, _run_tool_readonly, _safe_model_label
from comsol_mcp._model import _require_visible_main
from comsol_mcp._physics_ops import (
    _list_physics, _list_physics_features,
    _create_physics, _remove_physics,
    _create_physics_feature, _remove_physics_feature,
    _apply_physics_properties, _set_physics_selection,
    _list_variables, _create_variable, _remove_variable,
)


def list_physics(component: str = "comp1") -> str:
    """List all physics interfaces in a component with their features.

    Returns tags, labels, and feature counts for each physics interface.
    """

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("list_physics")
        comp = component.strip() or "comp1"
        physics_list = _list_physics(model, comp)
        return {
            "label": _safe_model_label(model),
            "component": comp,
            "physics": physics_list,
            "count": len(physics_list),
        }

    return _run_tool_readonly("list_physics", _impl)


def create_physics(component: str, tag: str, physics_type: str, dimension: int = 0, dependent_variables: str = "u") -> str:
    """Add a physics interface to a component.

    Common physics_type values: "cfpde" (Coefficient Form PDE),
    "tds" (Transport of Diluted Species), "solid" (Solid Mechanics),
    "ht" (Heat Transfer), "es" (Electrostatics), etc.

    dimension: spatial dimension (1, 2, or 3). Default 0 = auto-detect from
    the component's geometry. Set via configure_single_main_workflow(model_dimension=2).

    dependent_variables: comma-separated dependent variable names. Default "u".
    COMSOL uses these to create the correct physics with matching spatial dimension.
    For multiple dependent variables use "u,v" or "u,v,w".
    """

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("create_physics")
        comp = component.strip() or "comp1"
        phys_tag = tag.strip()
        ptype = physics_type.strip()
        dim = int(dimension)
        dep_vars = dependent_variables.strip() or "u"
        if not phys_tag:
            raise ValueError("Physics tag is required.")
        if not ptype:
            raise ValueError("physics_type is required.")
        result = _create_physics(model, comp, phys_tag, ptype, dim, dep_vars)
        return {"component": comp, **result}

    return _run_tool("create_physics", _impl)


def remove_physics(component: str, tag: str) -> str:
    """Remove a physics interface from a component."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("remove_physics")
        comp = component.strip() or "comp1"
        phys_tag = tag.strip()
        if not phys_tag:
            raise ValueError("Physics tag is required.")
        result = _remove_physics(model, comp, phys_tag)
        return {"component": comp, **result}

    return _run_tool("remove_physics", _impl)


def list_physics_features(component: str, physics_tag: str) -> str:
    """List all features (boundary conditions, sources, etc.) under a physics interface.

    Returns tags, labels, feature_type identifiers, property names, and
    selection editability for each feature. The feature_type field shows the
    COMSOL internal identifier to use with create_physics_feature.
    """

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("list_physics_features")
        comp = component.strip() or "comp1"
        phys = physics_tag.strip()
        if not phys:
            raise ValueError("physics_tag is required.")
        features = _list_physics_features(model, comp, phys)
        return {
            "label": _safe_model_label(model),
            "component": comp,
            "physics_tag": phys,
            "features": features,
            "count": len(features),
        }

    return _run_tool_readonly("list_physics_features", _impl)


def create_physics_feature(
    component: str,
    physics_tag: str,
    feature_tag: str,
    feature_type: str,
    properties_json: str = "[]",
) -> str:
    """Add a child feature (boundary condition, source term, etc.) to a physics interface.

    IMPORTANT: feature_type uses COMSOL internal identifiers, NOT display names.
    For example, in TDS (Transport of Diluted Species), valid types include:
    "Inflow", "Outflow", "Flux", "NoFlux", "Concentration", "InitialValues",
    "ConservedQuantity", "WeakConstraint".
    Use list_physics_features first to discover existing feature_type identifiers
    in the current physics interface, as these vary per physics type and COMSOL version.
    properties_json format: [{"name": "prop_name", "value": "value"}] or
    {"prop_name": "value", ...}.
    """

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("create_physics_feature")
        comp = component.strip() or "comp1"
        phys = physics_tag.strip()
        ftag = feature_tag.strip()
        ftype = feature_type.strip()
        if not phys:
            raise ValueError("physics_tag is required.")
        if not ftag:
            raise ValueError("feature_tag is required.")
        if not ftype:
            raise ValueError("feature_type is required.")
        result = _create_physics_feature(model, comp, phys, ftag, ftype)
        applied = []
        if properties_json.strip() and properties_json.strip() != "[]":
            applied = _apply_physics_properties(model, comp, phys, ftag, properties_json)
        return {"component": comp, "physics_tag": phys, **result, "properties_applied": applied}

    return _run_tool("create_physics_feature", _impl)


def update_physics_feature(
    component: str,
    physics_tag: str,
    feature_tag: str,
    properties_json: str,
) -> str:
    """Set properties on an existing physics feature.

    properties_json format: [{"name": "prop_name", "value": "value"}] or
    {"prop_name": "value", ...}. For array-valued properties use
    [{"name": "prop_name", "values": ["v1", "v2"]}].
    """

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("update_physics_feature")
        comp = component.strip() or "comp1"
        phys = physics_tag.strip()
        ftag = feature_tag.strip()
        if not phys:
            raise ValueError("physics_tag is required.")
        if not ftag:
            raise ValueError("feature_tag is required.")
        applied = _apply_physics_properties(model, comp, phys, ftag, properties_json)
        return {
            "component": comp,
            "physics_tag": phys,
            "feature_tag": ftag,
            "properties_applied": applied,
        }

    return _run_tool("update_physics_feature", _impl)


def remove_physics_feature(
    component: str,
    physics_tag: str,
    feature_tag: str,
) -> str:
    """Remove a child feature from a physics interface."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("remove_physics_feature")
        comp = component.strip() or "comp1"
        phys = physics_tag.strip()
        ftag = feature_tag.strip()
        if not phys:
            raise ValueError("physics_tag is required.")
        if not ftag:
            raise ValueError("feature_tag is required.")
        result = _remove_physics_feature(model, comp, phys, ftag)
        return {"component": comp, "physics_tag": phys, **result}

    return _run_tool("remove_physics_feature", _impl)


def set_physics_selection(
    component: str,
    physics_tag: str,
    feature_tag: str,
    entities_json: str,
) -> str:
    """Set domain, boundary, or edge selection for a physics feature.

    entities_json is a JSON array of integer entity IDs, e.g. "[1, 2, 3]".
    Some features have inherited selections that cannot be modified directly.
    Use list_physics_features to check selection_editable before calling this.
    If selection is not editable on a feature, try setting it on the parent
    physics interface instead (pass the physics tag as feature_tag).
    """

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("set_physics_selection")
        comp = component.strip() or "comp1"
        phys = physics_tag.strip()
        ftag = feature_tag.strip()
        if not phys:
            raise ValueError("physics_tag is required.")
        if not ftag:
            raise ValueError("feature_tag is required.")
        entities = json.loads(entities_json)
        if not isinstance(entities, list):
            raise ValueError("entities_json must be a JSON array of integers.")
        int_entities = [int(e) for e in entities]
        result = _set_physics_selection(model, comp, phys, ftag, int_entities)
        return {"component": comp, "physics_tag": phys, **result}

    return _run_tool("set_physics_selection", _impl)


def manage_variables(
    action: str,
    component: str = "",
    tag: str = "",
    name: str = "",
    expression: str = "",
) -> str:
    """Manage variable definitions: list, create, or remove.

    Actions:
    - "list": List all variables. Returns tags, names, and expressions.
    - "create": Create a variable node with given name and expression.
    - "remove": Remove a variable node by tag.

    When component is empty, operates on global variables.
    When component is specified, operates on component-level variables.
    """

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("manage_variables")
        act = action.strip().lower()
        comp = component.strip()

        if act == "list":
            variables = _list_variables(model, comp)
            return {
                "label": _safe_model_label(model),
                "scope": "component" if comp else "global",
                "component": comp or None,
                "variables": variables,
                "count": len(variables),
            }
        elif act == "create":
            vtag = tag.strip()
            vname = name.strip()
            vexpr = expression.strip()
            if not vtag:
                raise ValueError("Variable tag is required for create.")
            if not vname:
                raise ValueError("Variable name is required for create.")
            result = _create_variable(model, comp, vtag, vname, vexpr)
            return {"scope": "component" if comp else "global", "component": comp or None, **result}
        elif act == "remove":
            vtag = tag.strip()
            if not vtag:
                raise ValueError("Variable tag is required for remove.")
            result = _remove_variable(model, comp, vtag)
            return {"scope": "component" if comp else "global", "component": comp or None, **result}
        else:
            raise ValueError(f'Unknown action "{act}". Use "list", "create", or "remove".')

    return _run_tool("manage_variables", _impl)


def register(mcp_instance) -> None:
    mcp_instance.add_tool(list_physics)
    mcp_instance.add_tool(create_physics)
    mcp_instance.add_tool(remove_physics)
    mcp_instance.add_tool(list_physics_features)
    mcp_instance.add_tool(create_physics_feature)
    mcp_instance.add_tool(update_physics_feature)
    mcp_instance.add_tool(remove_physics_feature)
    mcp_instance.add_tool(set_physics_selection)
    mcp_instance.add_tool(manage_variables)
