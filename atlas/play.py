"""One episode of the atlas prototype: a case in (JSON on stdin), a result out, in the same shape as
`metasoar.play`'s so the two arms are measured alike. ARC-AGI-3 only for now."""
import json
import sys
import time
import warnings

from metasoar.envs import make

from atlas.agent import Atlas


def episode(case: dict) -> dict:
    t0 = time.perf_counter()
    env = make(case["env"], max_steps=int(case.get("max_steps", 500)))
    obs, _ = env.reset(seed=int(case["seed"]))
    u = env.unwrapped
    names = u.action_names()
    agent = Atlas(names, u.takes_point, seed=int(case["seed"]))
    total, steps, done, success, trace = 0.0, 0, False, False, []
    while not done:
        name, params = agent.step(obs)
        u.set_params(params or {})
        obs, reward, terminated, truncated, _ = env.step(names.index(name))
        steps += 1
        total += float(reward)
        done = terminated or truncated
        success = obs.get("state") == "WIN"
        if case.get("trace"):
            trace.append([name, params, agent.why, int(reward)])
    out = {"env": case["env"], "seed": case["seed"], "success": success, "return": round(total, 6), "steps": steps,
           "stuck_steps": 0, "invalid_steps": 0, "percept_failures": 0, "seconds": round(time.perf_counter() - t0, 3)}
    if case.get("trace"):
        out["trace"] = trace
    return out


def main():
    warnings.filterwarnings("ignore")
    print(json.dumps(episode(json.loads(sys.stdin.read()))))


if __name__ == "__main__":
    main()
