"""The environment adapter (docs/spec.md, "The only things we add"): any Gymnasium environment onto Soar's I/O.

Written once, for every environment, from the environment's own spaces: nothing here knows any game.

Input link, rebuilt each step under ^env:
  ^step N  ^reward R (the last step's)  ^done yes|no
  ^observation  the observation, by its space: a Dict as one attribute per key; Text and Discrete as a value;
                an array as ^cell elements, each with its index (^i, ^j, ...) and its values (^v0, ^v1, ...)
  ^actions      one ^action per action of a Discrete action space, with ^name (the environment's own name for it,
                where it gives one, else the number) and ^id
Output link: the agent writes (^act.action NAME); the adapter takes it, steps the environment, and marks the
command ^status complete. An agent that writes nothing within `patience` decision cycles is stuck: the step is
recorded as stuck and, by the hook's rule (M-03), is what goes to Substrate.
"""
from __future__ import annotations

import numpy as np
import Python_sml_ClientInterface as sml


def action_names(env) -> list[str]:
    n = env.action_space.n
    enum = getattr(env.unwrapped, "actions", None)
    try:
        return [enum(i).name for i in range(n)]
    except Exception:  # noqa: BLE001 - no names of its own: numbers
        return [str(i) for i in range(n)]


class Adapter:
    def __init__(self, agent, env):
        self.agent, self.env = agent, env
        self.names = action_names(env)
        self.input = agent.GetInputLink()
        self.root = None

    def _put(self, parent, attr, value):
        if isinstance(value, dict):
            node = self.agent.CreateIdWME(parent, attr)
            for k, v in value.items():
                self._put(node, str(k), v)
        elif isinstance(value, np.ndarray) and value.ndim >= 1:
            node = self.agent.CreateIdWME(parent, attr)
            cells = value.reshape(-1, value.shape[-1]) if value.ndim > 1 else value.reshape(-1, 1)
            shape = value.shape[:-1] if value.ndim > 1 else value.shape
            for flat, vals in enumerate(cells):
                cell = self.agent.CreateIdWME(node, "cell")
                for axis, idx in enumerate(np.unravel_index(flat, shape)):
                    self.agent.CreateIntWME(cell, "ijklmn"[axis], int(idx))
                for c, v in enumerate(vals):
                    self.agent.CreateIntWME(cell, f"v{c}", int(v))
        elif isinstance(value, (bool, np.bool_)):
            self.agent.CreateStringWME(parent, attr, "yes" if value else "no")
        elif isinstance(value, (int, np.integer)):
            self.agent.CreateIntWME(parent, attr, int(value))
        elif isinstance(value, (float, np.floating)):
            self.agent.CreateFloatWME(parent, attr, float(value))
        else:
            self.agent.CreateStringWME(parent, attr, str(value))

    def show(self, obs, step: int, reward: float, done: bool):
        if self.root is not None:
            self.agent.DestroyWME(self.root)
        self.root = self.agent.CreateIdWME(self.input, "env")
        self.agent.CreateIntWME(self.root, "step", step)
        self.agent.CreateFloatWME(self.root, "reward", float(reward))
        self.agent.CreateStringWME(self.root, "done", "yes" if done else "no")
        self._put(self.root, "observation", obs)
        acts = self.agent.CreateIdWME(self.root, "actions")
        for i, name in enumerate(self.names):
            a = self.agent.CreateIdWME(acts, "action")
            self.agent.CreateStringWME(a, "name", name)
            self.agent.CreateIntWME(a, "id", i)
        self.agent.Commit()

    def command(self, patience: int):
        """Run Soar until it writes an act command (Soar's own `run --output`), giving up after `patience` decisions
        with no output (Soar's `max-nil-output-cycles`). Returns (action index, -1 if not one of the actions, or
        None if none was written; decisions run)."""
        self.agent.ExecuteCommandLine(f"max-nil-output-cycles {patience}")
        before = self.agent.GetDecisionCycleCounter()
        self.agent.RunSelfTilOutput()
        n = self.agent.GetDecisionCycleCounter() - before
        for i in range(self.agent.GetNumberCommands()):
            cmd = self.agent.GetCommand(i)
            if cmd.GetCommandName() != "act" or cmd.GetParameterValue("status"):
                continue
            name = cmd.GetParameterValue("action")
            cmd.AddStatusComplete()
            self.agent.Commit()
            self.agent.ClearOutputLinkChanges()
            if name in self.names:
                return self.names.index(name), n
            if name is not None and name.isdigit() and int(name) < len(self.names):
                return int(name), n
            return -1, n
        self.agent.ClearOutputLinkChanges()
        return None, n
