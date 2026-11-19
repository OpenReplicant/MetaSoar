"""One episode, for Morphogen's judge and for trials: a case as JSON on stdin, the result as JSON on stdout.

    echo '{"env": "BabyAI-GoToLocal-v0", "seed": 7}' | python3 -I -m metasoar.play
    echo '{"env": "arc3:LS20", "seed": 0}' | python3 -I -m metasoar.play

Case fields: env (a Gymnasium id, or arc3:TITLE), seed, game (a held-out ARC-AGI-3 game's metadata and source, from
the judge's case; written to /tmp, loaded, and deleted before the agent starts), max_steps (default: the environment's own limit), patience
(decisions Soar may take per step before the step counts as stuck, default 50), trace (also return the mission and
the actions taken). The agent is `agent/main.soar` in the checkout (`/work` in the judge's sandbox), loaded into Soar
9.6.5 unchanged, with its perception, `agent/perception/main.py`, if it has one (M-09).

Perception runs in a process of its own: each step it gets one line of JSON ({"env", "step", "observation", "last": the
action just taken and its parameters, or null at the start}) on stdin
and answers one line of JSON, which goes onto the input link as ^percept. It cannot reach this process's output, so
it cannot change the result this prints; if it fails or takes longer than PERCEPT_SECONDS, the step goes on without
a percept (counted as percept_failures).

Result: success (the episode ended with positive reward, or the game won), return (summed reward: levels completed,
for ARC-AGI-3), steps, stuck_steps, invalid_steps, percept_failures, decisions, substate_decisions, seconds.
"""
from __future__ import annotations

import json
import select
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import Python_sml_ClientInterface as sml

from metasoar.adapter import Adapter
from metasoar.envs import make

AGENT = Path(__file__).resolve().parent.parent / "agent"
PERCEPT_SECONDS = 2.0


def jsonable(v):
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


class Perception:
    """The agent's perception in its own process, or nothing if the agent has none."""

    def __init__(self, env_id: str):
        self.env_id, self.proc, self.failures = env_id, None, 0
        main = AGENT / "perception" / "main.py"
        if main.is_file():
            self.proc = subprocess.Popen([sys.executable, "-I", str(main)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, cwd=str(main.parent), text=True, bufsize=1)

    def __call__(self, step: int, obs, last: dict | None = None) -> dict | None:
        if self.proc is None:
            return None
        try:
            self.proc.stdin.write(json.dumps({"env": self.env_id, "step": step, "observation": jsonable(obs),
                                              "last": last}) + "\n")
            self.proc.stdin.flush()
            ready, _, _ = select.select([self.proc.stdout], [], [], PERCEPT_SECONDS)
            if not ready:
                raise TimeoutError
            got = json.loads(self.proc.stdout.readline())
            return got if isinstance(got, dict) else None
        except Exception:  # noqa: BLE001 - a failed percept is counted, not fatal
            self.failures += 1
            return None

    def close(self):
        if self.proc is not None:
            self.proc.kill()


def episode(case: dict) -> dict:
    t0 = time.perf_counter()
    kw = {"max_steps": int(case["max_steps"])} if case.get("max_steps") else {}
    game_dir = None
    if case.get("game"):  # a held-out ARC-AGI-3 game, from the judge's case (M-09): never in the image
        import tempfile
        game_dir = Path(tempfile.mkdtemp(prefix="g", dir="/tmp"))
        g = case["game"]
        d = game_dir / g["metadata"]["game_id"].split("-")[0] / g["metadata"]["game_id"].split("-")[1]
        d.mkdir(parents=True)
        (d / "metadata.json").write_text(json.dumps({**g["metadata"], "local_dir": str(d)}))
        (d / g["file"]).write_text(g["source"])
        kw["games_dir"] = str(game_dir)
    env = make(case["env"], **kw)
    obs, _ = env.reset(seed=int(case["seed"]))
    if game_dir is not None:  # loaded: gone before the agent's perception (or anything of the agent's) starts
        import shutil
        shutil.rmtree(game_dir, ignore_errors=True)
    kernel = sml.Kernel.CreateKernelInCurrentThread(True, sml.Kernel.kSuppressListener)
    agent = kernel.CreateAgent("metasoar")
    agent.ExecuteCommandLine(f"srand {int(case['seed'])}")
    out = agent.ExecuteCommandLine(f"source {{{AGENT / 'main.soar'}}}")
    if not agent.GetLastCommandLineResult():
        raise SystemExit(f"the agent did not load: {out}")
    substate = [0]

    def after_decision(_id, _data, ag, _phase):
        if ag.ExecuteCommandLine("print --stack").strip().count("\n") > 0:
            substate[0] += 1

    agent.RegisterForRunEvent(sml.smlEVENT_AFTER_DECISION_CYCLE, after_decision, None)
    perceive = Perception(case["env"])
    ad = Adapter(agent, env)
    patience = int(case.get("patience", 50))
    total, steps, stuck, invalid, decisions, reward, done, success = 0.0, 0, 0, 0, 0, 0.0, False, False
    trace = [] if case.get("trace") else None
    mission = obs.get("mission") if isinstance(obs, dict) else None
    ad.show(obs, 0, 0.0, False, perceive(0, obs))
    set_params = getattr(env.unwrapped, "set_params", None)
    while not done:
        action, n = ad.command(patience)
        decisions += n
        if action is None:
            stuck += 1
            break
        if action < 0:
            invalid += 1
            action = None
        if trace is not None:
            trace.append(ad.names[action] if action is not None else None)
        info = {}
        if action is not None:
            if callable(set_params):
                set_params(ad.params)
            obs, reward, terminated, truncated, info = env.step(action)
            steps += 1
            total += float(reward)
            done = terminated or truncated
            won = isinstance(obs, dict) and obs.get("state") == "WIN"
            success = bool(won or (terminated and reward > 0 and "state" not in (obs if isinstance(obs, dict) else {})))
            invalid += 1 if info.get("invalid") else 0
        last = {"action": ad.names[action] if action is not None else None, "params": ad.params}
        ad.show(obs, steps, reward if action is not None else 0.0, done, perceive(steps, obs, last))
    perceive.close()
    kernel.Shutdown()
    return {"env": case["env"], "seed": case["seed"], "success": success, "return": round(total, 6), "steps": steps,
            "stuck_steps": stuck, "invalid_steps": invalid, "percept_failures": perceive.failures, "decisions": decisions,
            "substate_decisions": substate[0], "seconds": round(time.perf_counter() - t0, 3),
            **({"mission": mission, "actions": trace} if trace is not None else {})}


def main():
    warnings.filterwarnings("ignore")
    print(json.dumps(episode(json.loads(sys.stdin.read()))))


if __name__ == "__main__":
    main()
