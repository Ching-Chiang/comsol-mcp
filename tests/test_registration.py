"""Tests to verify all MCP tools are registered correctly."""

EXPECTED_TOOLS = [
    "server_info",
    "check_server_port",
    "workflow_info",
    "configure_single_main_workflow",
    "load_visible_main_model",
    "start_visible_main_workflow",
    "start_visible_main_workflow_async",
    "visible_main_workflow_status",
    "verify_visible_main_session",
    "unlock_visible_main",
    "mcp_tool_audit",
    "run_visible_main_iteration",
    "load_current_main_model",
    "save_main_model_snapshot",
    "commit_current_main_model",
    "prune_loaded_models",
    "server_start",
    "server_connect",
    "server_disconnect",
    "model_create",
    "model_load",
    "model_tree",
    "get_parameters",
    "evaluate_expressions",
    "get_core_metrics",
    "set_parameters",
    "ensure_component",
    "ensure_geometry",
    "ensure_mesh",
    "create_feature",
    "update_feature",
    "delete_feature",
    "run_feature",
    "run_study",
    "save_model",
    "list_physics",
    "create_physics",
    "remove_physics",
    "list_physics_features",
    "create_physics_feature",
    "update_physics_feature",
    "remove_physics_feature",
    "set_physics_selection",
    "manage_variables",
    "list_solver_config",
    "create_solver_config",
    "list_solver_features",
    "configure_solver",
    "run_study_async",
    "run_study_status",
]


def test_all_tools_registered():
    import comsol_mcp.mcp_server
    from comsol_mcp._server import mcp

    registered = set(mcp._tool_manager._tools.keys())
    expected = set(EXPECTED_TOOLS)
    assert registered == expected, (
        f"Missing: {expected - registered}, "
        f"Extra: {registered - expected}"
    )


def test_tool_count():
    import comsol_mcp.mcp_server
    from comsol_mcp._server import mcp

    assert len(mcp._tool_manager._tools) == len(EXPECTED_TOOLS)
