"""Tests for tool classification sets."""

from comsol_mcp._server import SAFE_READ_TOOLS, SAFE_VISIBLE_MAIN_WRITE_TOOLS, RESTRICTED_TOOLS


def test_classification_sets_disjoint():
    read = SAFE_READ_TOOLS
    write = SAFE_VISIBLE_MAIN_WRITE_TOOLS
    restricted = RESTRICTED_TOOLS

    assert read.isdisjoint(write), f"Read/Write overlap: {read & write}"
    assert read.isdisjoint(restricted), f"Read/Restricted overlap: {read & restricted}"
    assert write.isdisjoint(restricted), f"Write/Restricted overlap: {write & restricted}"


def test_all_classified_tools_are_registered():
    import comsol_mcp.mcp_server
    from comsol_mcp._server import mcp

    registered = set(mcp._tool_manager._tools.keys())
    classified = SAFE_READ_TOOLS | SAFE_VISIBLE_MAIN_WRITE_TOOLS | RESTRICTED_TOOLS
    assert classified.issubset(registered), f"Classified but not registered: {classified - registered}"
