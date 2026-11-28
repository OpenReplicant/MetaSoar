"""The standard OpenEnv HTTP and WebSocket app for manager-env.

    cd trials/manager-env && python3 -m uvicorn server.app:app --port 8000
    MANAGER_ENV_OPTIONS='{"dedupe": true}' python3 -m uvicorn server.app:app     # env options, as JSON

Endpoints (OpenEnv's): POST /reset {"scenario_id": "s01"} (or {"seed": 3}), POST /step with a ManagerAction
({"action": {"type": "call_tool", "tool_name": "pm_portfolio", "arguments": {}}} or {"action": {"type": "end_turn",
"text": "..."}}), GET /state, GET /schema, WS /ws. Plain HTTP /step is one call on a fresh environment: for an episode
use the WebSocket or OpenEnv's client, which hold a session.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from openenv.core.env_server.http_server import create_app  # noqa: E402

from manager_env import ManagerAction, ManagerEnvironment, ManagerObservation  # noqa: E402

app = create_app(ManagerEnvironment, ManagerAction, ManagerObservation, env_name="manager-env", max_concurrent_envs=4)


def main(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    main(port=ap.parse_args().port)
