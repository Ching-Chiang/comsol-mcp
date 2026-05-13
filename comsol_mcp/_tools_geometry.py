#!/usr/bin/env python3
"""MCP tools: ensure_component, ensure_geometry, ensure_mesh, create/update/delete/run_feature."""

from __future__ import annotations

from typing import Any

from comsol_mcp._state import _run_tool
from comsol_mcp._model import _require_visible_main
from comsol_mcp._model_ops import (
    _normalize_properties, _ensure_geometry_java, _apply_feature_properties,
)


def ensure_component(component: str = "comp1", dimension: int = 2) -> str:
    """Ensure a component exists in the selected server-side model."""

    def _impl() -> dict[str, Any]:
        from comsol_mcp._model_ops import _ensure_component_java
        return _ensure_component_java(_require_visible_main("ensure_component"), component.strip() or "comp1", int(dimension))

    return _run_tool("ensure_component", _impl)


def ensure_geometry(component: str = "comp1", geometry: str = "geom1", dimension: int = 2) -> str:
    """Ensure a geometry sequence exists in the selected server-side model."""

    def _impl() -> dict[str, Any]:
        return _ensure_geometry_java(
            _require_visible_main("ensure_geometry"),
            component.strip() or "comp1",
            geometry.strip() or "geom1",
            int(dimension),
        )

    return _run_tool("ensure_geometry", _impl)


def ensure_mesh(component: str = "comp1", mesh: str = "mesh1") -> str:
    """Ensure a mesh sequence exists in the selected server-side model."""

    def _impl() -> dict[str, Any]:
        from comsol_mcp._model_ops import _ensure_mesh_java
        return _ensure_mesh_java(_require_visible_main("ensure_mesh"), component.strip() or "comp1", mesh.strip() or "mesh1")

    return _run_tool("ensure_mesh", _impl)


def create_feature(
    component: str,
    geometry: str,
    tag: str,
    feature_type: str,
    properties_json: str = "[]",
    run_geometry: bool = False,
) -> str:
    """Create a geometry feature and optionally apply initial properties."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("create_feature")
        comp = component.strip() or "comp1"
        geom = geometry.strip() or "geom1"
        feature_tag = tag.strip()
        kind = feature_type.strip()
        if not feature_tag:
            raise ValueError("Feature tag is required.")
        if not kind:
            raise ValueError("feature_type is required.")
        _ensure_geometry_java(model, comp, geom, 2)
        feature_container = model.java.component(comp).geom(geom).feature()
        if feature_tag not in list(feature_container.tags()):
            model.java.component(comp).geom(geom).create(feature_tag, kind)
        feature = model.java.component(comp).geom(geom).feature(feature_tag)
        applied = _apply_feature_properties(feature, _normalize_properties(properties_json))
        if run_geometry:
            model.java.component(comp).geom(geom).run()
        return {
            "component": comp,
            "geometry": geom,
            "tag": feature_tag,
            "feature_type": kind,
            "properties": applied,
            "run_geometry": bool(run_geometry),
        }

    return _run_tool("create_feature", _impl)


def update_feature(
    component: str,
    geometry: str,
    tag: str,
    properties_json: str,
    run_geometry: bool = False,
) -> str:
    """Update geometry feature properties on the selected server-side model."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("update_feature")
        comp = component.strip() or "comp1"
        geom = geometry.strip() or "geom1"
        feature_tag = tag.strip()
        if not feature_tag:
            raise ValueError("Feature tag is required.")
        _ensure_geometry_java(model, comp, geom, 2)
        feature_container = model.java.component(comp).geom(geom).feature()
        if feature_tag not in list(feature_container.tags()):
            raise LookupError(f'Feature "{feature_tag}" does not exist.')
        feature = model.java.component(comp).geom(geom).feature(feature_tag)
        applied = _apply_feature_properties(feature, _normalize_properties(properties_json))
        if run_geometry:
            model.java.component(comp).geom(geom).run()
        return {
            "component": comp,
            "geometry": geom,
            "tag": feature_tag,
            "properties": applied,
            "run_geometry": bool(run_geometry),
        }

    return _run_tool("update_feature", _impl)


def delete_feature(component: str, geometry: str, tag: str, run_geometry: bool = False) -> str:
    """Delete a geometry feature from the selected server-side model."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("delete_feature")
        comp = component.strip() or "comp1"
        geom = geometry.strip() or "geom1"
        feature_tag = tag.strip()
        if not feature_tag:
            raise ValueError("Feature tag is required.")
        feature_container = model.java.component(comp).geom(geom).feature()
        if feature_tag not in list(feature_container.tags()):
            raise LookupError(f'Feature "{feature_tag}" does not exist.')
        feature_container.remove(feature_tag)
        if run_geometry:
            model.java.component(comp).geom(geom).run()
        return {
            "component": comp,
            "geometry": geom,
            "tag": feature_tag,
            "run_geometry": bool(run_geometry),
        }

    return _run_tool("delete_feature", _impl)


def run_feature(collection: str, tag: str, component: str = "comp1") -> str:
    """Run a geometry or mesh sequence on the selected server-side model."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("run_feature")
        comp = component.strip() or "comp1"
        seq_tag = tag.strip()
        kind = collection.strip().lower()
        if not seq_tag:
            raise ValueError("Feature tag is required.")
        if kind == "geometry":
            model.java.component(comp).geom(seq_tag).run()
        elif kind == "mesh":
            model.java.component(comp).mesh(seq_tag).run()
        else:
            raise ValueError('collection must be "geometry" or "mesh".')
        return {"collection": kind, "component": comp, "tag": seq_tag}

    return _run_tool("run_feature", _impl)


def register(mcp_instance) -> None:
    mcp_instance.add_tool(ensure_component)
    mcp_instance.add_tool(ensure_geometry)
    mcp_instance.add_tool(ensure_mesh)
    mcp_instance.add_tool(create_feature)
    mcp_instance.add_tool(update_feature)
    mcp_instance.add_tool(delete_feature)
    mcp_instance.add_tool(run_feature)
