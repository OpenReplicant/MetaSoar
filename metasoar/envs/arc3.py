"""ARC-AGI-3 games (arc-agi 0.9.9, arcengine 0.9.3; MIT) as a Gymnasium environment, run offline from local files.

Observation (a Dict): `frame`, the last 64x64 grid of colours 0..15 the game shows; `levels_completed`; `state`
(NOT_FINISHED, WIN, GAME_OVER). Actions: the game's own available actions, by their names (ACTION1..ACTION7);
one that takes a point (ACTION6) reads `x` and `y` from the command's parameters (`set_params`), and is invalid
without them. Reward: 1 for each level completed on that step. The episode ends at WIN or GAME_OVER, or at
`max_steps` (default 500). Nothing here knows any game: it is the toolkit's own interface.
"""
from __future__ import annotations

import logging
import os

import gymnasium as gym
import numpy as np

GAMES = os.environ.get("ARC3_GAMES", "/opt/arc3/environment_files")


class Arc3Env(gym.Env):
    def __init__(self, title: str, max_steps: int = 500, games_dir: str | None = None):
        logging.disable(logging.CRITICAL)
        from arc_agi import Arcade, OperationMode
        from arcengine import GameAction
        self.GameAction = GameAction
        self.arc = Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=games_dir or GAMES,
                          recordings_dir="/tmp/arc3-recordings")
        ids = [e.game_id for e in self.arc.get_environments() if e.title.upper() == title.upper()]
        if not ids:
            raise ValueError(f"no ARC-AGI-3 game {title} in {games_dir or GAMES}")
        self.game_id, self.max_steps, self.params = ids[0], max_steps, {}
        self.env = None
        self.action_space = gym.spaces.Discrete(1)

    def _obs(self, fd):
        frames = np.asarray(fd.frame) if fd.frame is not None else np.zeros((1, 64, 64), dtype=np.int64)
        return {"frame": frames[-1].astype(np.int64), "levels_completed": int(fd.levels_completed), "state": fd.state.name}

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.env = self.arc.make(self.game_id, seed=int(seed or 0))
        fd = self.env.reset()
        self.available = [a for a in self.GameAction if a.value in (fd.available_actions or []) and a.name != "RESET"]
        self.action_space = gym.spaces.Discrete(len(self.available))
        self.steps, self.levels = 0, int(fd.levels_completed)
        self._last = self._obs(fd)
        return self._last, {}

    def action_names(self):
        return [a.name for a in self.available]

    def takes_point(self, index: int) -> bool:
        return self.available[index].is_complex()

    def set_params(self, params: dict):
        self.params = params or {}

    def step(self, action):
        a = self.available[int(action)]
        data = {}
        if a.is_complex():
            try:
                data = {"x": max(0, min(63, int(self.params["x"]))), "y": max(0, min(63, int(self.params["y"])))}
            except (KeyError, TypeError, ValueError):
                self.steps += 1
                fd = None
                return self._last, 0.0, False, self.steps >= self.max_steps, {"invalid": True}
        fd = self.env.step(a, data=data)
        self.steps += 1
        obs = self._obs(fd)
        self._last = obs
        reward = float(obs["levels_completed"] - self.levels)
        self.levels = obs["levels_completed"]
        terminated = obs["state"] in ("WIN", "GAME_OVER")
        return obs, reward, terminated, self.steps >= self.max_steps, {}
