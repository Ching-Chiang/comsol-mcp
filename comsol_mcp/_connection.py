#!/usr/bin/env python3
"""Connection lifecycle: disconnect, client shell management, require_client."""

from __future__ import annotations

import logging
from typing import Any

from comsol_mcp._server import (
    _client, _client_connected, _connected_host, _connected_port,
    _server, _current_model, _current_model_origin, _current_model_path,
    _server_started_by_mcp,
    _get_mph,
)
import comsol_mcp._server as _srv


def _disconnect_locked(*, shutdown_server: bool = False) -> None:
    if _srv._client is not None:
        try:
            _srv._client.disconnect()
        except Exception as exc:
            if "not connected" not in str(exc).lower():
                _srv._last_error = f"Disconnect failed: {exc}"
        finally:
            _srv._client_connected = False
            _srv._connected_host = ""
            _srv._connected_port = None

    _srv._current_model = None
    _srv._current_model_origin = ""
    _srv._current_model_path = ""

    if shutdown_server and _srv._server is not None and _srv._server_started_by_mcp:
        try:
            _srv._server.stop()
        except Exception as exc:
            _srv._last_error = f"Server stop failed: {exc}"
        finally:
            _srv._server = None
            _srv._server_started_by_mcp = False
    elif shutdown_server:
        _srv._server = None
        _srv._server_started_by_mcp = False


def _ensure_client_shell() -> Any:
    if _srv._client is None:
        mph = _get_mph()
        if mph is None:
            raise RuntimeError("MPh is not available; cannot create client shell.")
        _srv._client = mph.Client(host=None)
    return _srv._client


def _require_client() -> Any:
    if _srv._client is None or not _srv._client_connected:
        raise RuntimeError("Not connected to a COMSOL Multiphysics Server.")
    return _srv._client
