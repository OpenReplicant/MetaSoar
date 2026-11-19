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
    library = {}
    for path in case.get("library_in") or []:  # libraries from other games, merged
        try:
            for look, whats in json.load(open(path)).items():
                for what, c in whats.items():
                    for o, n in c.items():
                        library.setdefault(look, {}).setdefault(what, {})
                        library[look][what][o] = library[look][what].get(o, 0) + n
        except (OSError, ValueError):
            pass
    proposer = None
    if case.get("propose"):  # the model tier: {"cache": dir, "model": id}; needs the network
        from atlas.propose import MODEL, Proposer
        proposer = Proposer(case["propose"].get("cache"), model=case["propose"].get("model", MODEL))
    agent = Atlas(names, u.takes_point, seed=int(case["seed"]), library=library,
                  lock_rule=case.get("lock_rule", True), proposer=proposer)
    total, steps, done, success, trace = 0.0, 0, False, False, []
    while not done:
        name, params = agent.step(obs)
        u.set_params(params or {})
        obs, reward, terminated, truncated, _ = env.step(names.index(name))
        steps += 1
        total += float(reward)
        done = terminated or truncated
        success = obs.get("state") == "WIN"
        trace.append([name, params, agent.why, int(reward)])
    if case.get("library_out"):
        json.dump(agent.export(), open(case["library_out"], "w"))
    out = {"env": case["env"], "seed": case["seed"], "success": success, "return": round(total, 6), "steps": steps,
           "stuck_steps": 0, "invalid_steps": 0, "percept_failures": 0, "seconds": round(time.perf_counter() - t0, 3)}
    out["first_level"] = next((i + 1 for i, t in enumerate(trace) if t[3]), None)
    out["library_size"] = len(library)
    if proposer is not None:
        out["proposals"] = proposer.calls
    if case.get("trace"):
        out["trace"] = trace
    return out


def main():
    warnings.filterwarnings("ignore")
    print(json.dumps(episode(json.loads(sys.stdin.read()))))


if __name__ == "__main__":
    main()
