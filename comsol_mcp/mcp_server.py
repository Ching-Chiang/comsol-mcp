#!/usr/bin/env python3
"""COMSOL MCP Server - entrypoint and tool registration.

Server-first MCP bridge for COMSOL Multiphysics. It manages a COMSOL
Multiphysics Server process (or connects to an existing one), then drives the
same server-side model that a COMSOL Desktop client can visualize.
"""

from comsol_mcp._server import mcp, _setup_logging
from comsol_mcp._state import _write_status
from comsol_mcp._tools_connection import register as _reg_connection
from comsol_mcp._tools_workflow import register as _reg_workflow
from comsol_mcp._tools_model import register as _reg_model
from comsol_mcp._tools_params import register as _reg_params
from comsol_mcp._tools_geometry import register as _reg_geometry
from comsol_mcp._tools_snapshot import register as _reg_snapshot
from comsol_mcp._tools_physics import register as _reg_physics
from comsol_mcp._tools_solver import register as _reg_solver

# Register all tools on the shared FastMCP instance at import time.
_reg_connection(mcp)
_reg_workflow(mcp)
_reg_model(mcp)
_reg_params(mcp)
_reg_geometry(mcp)
_reg_snapshot(mcp)
_reg_physics(mcp)
_reg_solver(mcp)


def main() -> None:
    _setup_logging()
    _write_status({"status": "ready"})
    mcp.run()


if __name__ == "__main__":
    main()
