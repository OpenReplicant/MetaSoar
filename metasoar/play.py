"""One episode, for Morphogen's judge and for trials: a case as JSON on stdin, the result as JSON on stdout.

    echo '{"env": "BabyAI-GoToLocal-v0", "seed": 7}' | python3 -I -m metasoar.play

Case fields: env (a Gymnasium id), seed, max_steps (default: the environment's own limit), patience (decisions
Soar may take per step before the step counts as stuck, default 50). The agent is `agent/main.soar` in the checkout
(`/work` in the judge's sandbox), loaded into Soar 9.6.5 unchanged.

Result: success (the episode ended with positive reward), return, steps, stuck_steps, invalid_steps, decisions,
substate_decisions (decisions taken below the top state: Soar's own problem solving), seconds.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import gymnasium as gym
import minigrid  # noqa: F401 - registers the MiniGrid and BabyAI environments
import Python_sml_ClientInterface as sml

from metasoar.adapter import Adapter

AGENT = Path(__file__).resolve().parent.parent / "agent" / "main.soar"


def episode(case: dict) -> dict:
    t0 = time.perf_counter()
    env = gym.make(case["env"], max_steps=case["max_steps"]) if case.get("max_steps") else gym.make(case["env"])
    obs, _ = env.reset(seed=int(case["seed"]))
    kernel = sml.Kernel.CreateKernelInCurrentThread(True, sml.Kernel.kSuppressListener)
    agent = kernel.CreateAgent("metasoar")
    agent.ExecuteCommandLine(f"srand {int(case['seed'])}")
    out = agent.ExecuteCommandLine(f"source {{{AGENT}}}")
    if not agent.GetLastCommandLineResult():
        raise SystemExit(f"the agent did not load: {out}")
    substate = [0]

    def after_decision(_id, _data, ag, _phase):
        if ag.ExecuteCommandLine("print --stack").strip().count("\n") > 0:
            substate[0] += 1

    agent.RegisterForRunEvent(sml.smlEVENT_AFTER_DECISION_CYCLE, after_decision, None)
    ad = Adapter(agent, env)
    patience = int(case.get("patience", 50))
    total, steps, stuck, invalid, decisions, reward, done, success = 0.0, 0, 0, 0, 0, 0.0, False, False
    ad.show(obs, 0, 0.0, False)
    while not done:
        action, n = ad.command(patience)
        decisions += n
        if action is None:
            stuck += 1
            break
        if action < 0:
            invalid += 1
            action = None
        if action is not None:
            obs, reward, terminated, truncated, _ = env.step(action)
            steps += 1
            total += float(reward)
            done = terminated or truncated
            success = bool(terminated and reward > 0)
        ad.show(obs, steps, reward if action is not None else 0.0, done)
    kernel.Shutdown()
    return {"env": case["env"], "seed": case["seed"], "success": success, "return": round(total, 6), "steps": steps,
            "stuck_steps": stuck, "invalid_steps": invalid, "decisions": decisions,
            "substate_decisions": substate[0], "seconds": round(time.perf_counter() - t0, 3)}


def main():
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    import warnings
    warnings.filterwarnings("ignore")
    print(json.dumps(episode(json.loads(sys.stdin.read()))))


if __name__ == "__main__":
    main()
