#!/usr/bin/env python3
"""Run the budget gateway and Logits translator in one credential sidecar."""

from __future__ import annotations

import os
import signal
from http.server import ThreadingHTTPServer
from pathlib import Path

from logits_openai_bridge import (
    DEFAULT_MODEL_ASSETS_ROOT,
    start_bridge_server,
)


def _read_gateway_key() -> str:
    path = os.environ.get("PDDL_GATEWAY_API_KEY_FILE")
    if path:
        value = Path(path).read_text(encoding="utf-8")
    else:
        value = os.environ.get("PDDL_GATEWAY_API_KEY", "")
    if not value:
        raise SystemExit("gateway API key is required")
    return value


def main() -> None:
    model = os.environ.get("PDDL_LOGITS_MODEL", "")
    if not model:
        raise SystemExit("PDDL_LOGITS_MODEL is required")
    port = int(os.environ.get("PDDL_LOGITS_BRIDGE_PORT", "8769"))
    origin = os.environ.get("PDDL_LOGITS_ORIGIN", "https://api.logits.dev")
    assets_root = Path(
        os.environ.get("PDDL_LOGITS_MODEL_ASSETS_ROOT", str(DEFAULT_MODEL_ASSETS_ROOT))
    )
    ledger_path = os.environ.get("PDDL_LOGITS_LEDGER_PATH")
    server = backend = thread = gateway_module = gateway_server = None
    try:
        server, backend, thread = start_bridge_server(
            bind="127.0.0.1",
            port=port,
            model=model,
            api_key=_read_gateway_key(),
            ledger_path=Path(ledger_path) if ledger_path else None,
            assets_root=assets_root,
            origin=origin,
        )
        # Import only after replacing the external origin with the loopback
        # translator. model_gateway reads and validates its env at import time.
        os.environ["PDDL_GATEWAY_UPSTREAM_ORIGIN"] = f"http://127.0.0.1:{port}"
        import model_gateway

        gateway_module = model_gateway

        with model_gateway.State.lock:
            model_gateway._publish_control_locked()
        gateway_server = ThreadingHTTPServer(
            (model_gateway.LISTEN_HOST, model_gateway.LISTEN_PORT),
            model_gateway.GatewayHandler,
        )

        def _terminate(_signum, _frame):
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _terminate)
        signal.signal(signal.SIGINT, _terminate)
        gateway_server.serve_forever()
    finally:
        if gateway_server is not None:
            gateway_server.server_close()
        if gateway_module is not None:
            gateway_module.INFRA_DIAGNOSTICS.close(timeout=2.0)
        if server is not None:
            server.shutdown()
            server.server_close()
        if backend is not None:
            backend.close()
        if thread is not None:
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
