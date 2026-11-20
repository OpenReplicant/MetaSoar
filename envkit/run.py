"""One run: an environment from its declaration, an agent attached to what it exposes, taps, and a scheduler.

    python3 -m envkit.run arc3 --param game=LS20 --param seed=0 --agent atlas [--realtime --speed 4] [--film run.gif] [--live 8765]

prints the run as one line of JSON (levels or return, steps, the end event). The agent is chosen here, not in the
declaration: the environment is the world side, the agent is the candidate's (README.md, "Custody").
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings

from envkit.core import Lockstep, Realtime, attach
from envkit.declare import load
from envkit.modules import PolicyAgent, Recorder


def atlas_agent(seed: int, **opts):
    from atlas.agent import Atlas

    def build(actions):
        points = actions["points"]
        return Atlas(actions["names"], lambda i: points[i], seed=seed, **opts)

    return PolicyAgent("agent", build, observe=["frame", "attempt", "levels_completed", "state"])


AGENTS = {"atlas": atlas_agent}


def run(env_name: str, params: dict, agent: str = "atlas", profile: str | None = "judged", realtime: bool = False,
        speed: float = 1.0, agent_opts: dict | None = None, film: str | None = None, film_every: int = 2, live: int | None = None):
    env = load(env_name, **params)
    a = AGENTS[agent](int(env.params.get("seed", 0)), **(agent_opts or {}))
    attach(env, a, {p: p for p in a.inputs if p in env.expose} | {"cmd": "cmd"}, profile=profile)
    rec = Recorder("record", ["reward", "event"])
    attach(env, rec, {"reward": "reward", "event": "event"})
    modules = env.modules + [a, rec]
    from envkit.watch import Film, Live
    for f in ([Film("film", film, every=film_every)] if film else []) + ([Live("live", live)] if live else []):
        attach(env, f, {"screen": "screen" if "screen" in env.expose else "frame", "reward": "reward",
                        "event": "event", "tick": "tick"} | {p: p for p in ("things", "camera") if p in env.expose})
        f.wired_in["why"] = a.wired_out.get("why", f"{a.name}.why")  # a tap may read the agent too
        modules.append(f)
    t0 = time.perf_counter()
    ticks = (Realtime(modules, speed=speed).run() if realtime else Lockstep(modules).run())
    rewards = [(t, d) for t, p, d in rec.log if p == "reward" and d]
    end = next((d for t, p, d in rec.log if p == "event" and d["kind"] == "end"), None)
    return {"env": env_name, "params": env.params, "return": sum(d for _, d in rewards),
            "reward_ticks": [t for t, _ in rewards], "end": end, "ticks": ticks,
            "seconds": round(time.perf_counter() - t0, 3)}


def main(argv=None):
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("env")
    ap.add_argument("--param", action="append", default=[], help="name=value (ints are read as ints)")
    ap.add_argument("--agent", default="atlas")
    ap.add_argument("--profile", default="judged")
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--film", help="write the run as an animated GIF with the agent's reasons beside it")
    ap.add_argument("--film-every", type=int, default=2)
    ap.add_argument("--live", type=int, metavar="PORT", help="serve the run as it happens on 127.0.0.1:PORT")
    a = ap.parse_args(argv)
    params = {}
    for kv in a.param:
        k, _, v = kv.partition("=")
        params[k] = int(v) if v.lstrip("-").isdigit() else v
    print(json.dumps(run(a.env, params, a.agent, a.profile or None, a.realtime, a.speed,
                         film=a.film, film_every=a.film_every, live=a.live)))


if __name__ == "__main__":
    sys.exit(main())
