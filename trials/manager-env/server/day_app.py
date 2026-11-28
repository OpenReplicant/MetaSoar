"""The OpenEnv HTTP and WebSocket app for tier 2 (the day environment).

    cd trials/manager-env && python3 -m uvicorn server.day_app:app --port 8001
    MANAGER_DAY_OPTIONS='{"owner_first": true, "speed": 2}' python3 -m uvicorn server.day_app:app

POST /reset {"day_id": "train-00"} (or {"seed": 3}); steps are DayAction ({"type": "call_tool", ...} or {"type": "end_turn",
"seconds": 12.5}). A day is many steps, so use the WebSocket or OpenEnv's client, which hold a session.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from openenv.core.env_server.http_server import create_app  # noqa: E402

from manager_env import DayAction, DayEnvironment, DayObservation  # noqa: E402

app = create_app(DayEnvironment, DayAction, DayObservation, env_name="manager-env-day", max_concurrent_envs=4)
