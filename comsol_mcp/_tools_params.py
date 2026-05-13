#!/usr/bin/env python3
"""MCP tools: get_parameters, set_parameters, evaluate_expressions, get_core_metrics."""

from __future__ import annotations

import json
from typing import Any

from comsol_mcp._state import (
    _run_tool, _safe_model_label,
)
from comsol_mcp._model import _require_visible_main
from comsol_mcp._model_ops import (
    _parameter_rows, _evaluate_named_expressions,
    _find_initialized_solution_tag, _read_last_time_day,
    _eval_global_last, _eval_domain_average_last,
    _eval_boundary_average_last, _eval_extremum_last,
    _numeric_result,
)


def get_parameters() -> str:
    """Return current global parameters from the selected server-side model."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("get_parameters")
        rows = _parameter_rows(model)
        return {"label": _safe_model_label(model), "parameters": rows, "count": len(rows)}

    return _run_tool("get_parameters", _impl)


def evaluate_expressions(expressions_json: str = "[]") -> str:
    """Evaluate one or more expressions on the current server-side model."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("evaluate_expressions")
        parsed = json.loads(expressions_json)
        if not isinstance(parsed, list):
            raise ValueError("expressions_json must be a JSON array.")
        results = _evaluate_named_expressions(model, parsed)
        return {
            "label": _safe_model_label(model),
            "results": results,
            "count": len(results),
        }

    return _run_tool("evaluate_expressions", _impl)


def get_core_metrics() -> str:
    """Return the core metrics used by the current short-window mainline."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("get_core_metrics")
        cover_domains = [1, 2]
        steel_boundaries = [5, 6, 7, 8]
        sol_tag = _find_initialized_solution_tag(model)
        last_time_day = _read_last_time_day(model, sol_tag)

        w_acc_avg = _eval_global_last(model, "wAccAvg")
        if w_acc_avg is None:
            w_acc_avg = _eval_domain_average_last(model, "w_acc", cover_domains)

        phi_loc_max = _eval_extremum_last(model, "MaxSurface", "phi_loc", cover_domains)
        ccl_steel_avg = _eval_boundary_average_last(model, "cCl", steel_boundaries)

        eta_avg = _eval_global_last(model, "etaAvg")
        if eta_avg is None:
            eta_avg = _eval_domain_average_last(model, "etaClamp", cover_domains)

        steel_mass_loss = _eval_global_last(model, "steelMassLoss")

        results = [
            _numeric_result("last_time_day", "sol.getPVals()/86400", last_time_day, ok=last_time_day is not None, error="NA"),
            _numeric_result("wAccAvg", "wAccAvg | avg(w_acc)", w_acc_avg, ok=w_acc_avg is not None, error="NA"),
            _numeric_result("phiLocMax", "max(phi_loc)", phi_loc_max, ok=phi_loc_max is not None, error="NA"),
            _numeric_result("cClSteelAvg", "avg_boundary(cCl)", ccl_steel_avg, ok=ccl_steel_avg is not None, error="NA"),
            _numeric_result("etaAvg", "etaAvg | avg(etaClamp)", eta_avg, ok=eta_avg is not None, error="NA"),
            _numeric_result("steelMassLoss", "steelMassLoss", steel_mass_loss, ok=steel_mass_loss is not None, error="NA"),
        ]
        ok_map = {row["name"]: row.get("ok", False) for row in results}
        solve_status = "success" if all(ok_map.get(name, False) for name in ("wAccAvg", "phiLocMax", "cClSteelAvg")) else "partial"
        return {
            "label": _safe_model_label(model),
            "solve_status": solve_status,
            "solution_tag": sol_tag,
            "results": results,
        }

    return _run_tool("get_core_metrics", _impl)


def set_parameters(parameters_json: str) -> str:
    """Set multiple global parameters on the selected server-side model."""

    def _impl() -> dict[str, Any]:
        model = _require_visible_main("set_parameters")
        parsed = json.loads(parameters_json)
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
        return {"updated": updated, "count": len(updated)}

    return _run_tool("set_parameters", _impl)


def register(mcp_instance) -> None:
    mcp_instance.add_tool(get_parameters)
    mcp_instance.add_tool(evaluate_expressions)
    mcp_instance.add_tool(get_core_metrics)
    mcp_instance.add_tool(set_parameters)
