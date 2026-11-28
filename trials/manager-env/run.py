"""Rollouts: an OpenAI-compatible chat endpoint driven through manager-env, for scenarios and candidates.

    python3 run.py --arm inkling --url http://127.0.0.1:8081 --model inkling [--candidates cands.json] [--only s01,s02]
        [--out-dir DIR] [--resume] [--env '{"dedupe": true}'] [--id base] [--prompt prompts/c0.md] [--extra JSON] [--prefill auto]

cands.json is gepa.py's: {"candidates": [{"id", "prompt", "env", "extra", "prefill"}]}; without it, one candidate (`--id`,
default "base": manager.md, no env options, unless --prompt/--env/--extra/--prefill are given).
For each candidate it writes, in DIR (default trials/manager-eval/pm1a/results/gepa-env):
    <arm>-<id>.json          replay.py's results format (replay.py report, gepa.py summary read it)
    <arm>-<id>.rollouts/     OpenEnv harness records: results.jsonl (one EpisodeRecord per line, `messages` form for TRL's
                             SFTTrainer, with reward, tool_trace and the score dict as verify_metrics) and metadata.json
The model request is drivers.OpenAICompatible.turn (prefill, extra, max_tokens as there). The environment, not the driver,
applies inline_portfolio, dedupe, search_budget, final_nudge and the step limit.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from manager_env import ManagerAction, ManagerEnvironment, _pm1a  # noqa: E402
import drivers  # noqa: E402
import gepa  # noqa: E402

from openenv.core.harness.collect import EpisodeRecord, RolloutSerializer  # noqa: E402

DEFAULT_DIR = os.path.join(_pm1a.PM1A_DIR, "results", "gepa-env")


def play(env, driver, scenario_id, log=print):
    """One episode: the model's turns as env steps. Returns (final observation, messages, tool_trace, usage)."""
    obs = env.reset(scenario_id=scenario_id)
    msgs = [{"role": "system", "content": driver.prompt}, {"role": "user", "content": obs.message}]
    tool_trace, tok = [], drivers.tokens()
    while not obs.done:
        if obs.nudge:
            msgs.append({"role": "user", "content": obs.nudge})
        r = driver.turn(msgs)
        u = r.get("usage") or {}
        tok = drivers.tokens(tok["input"] + u.get("prompt_tokens", 0), tok["output"] + u.get("completion_tokens", 0),
                             turns=tok["turns"] + 1)
        m = r["choices"][0]["message"]
        msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls") and v is not None})
        content, calls = m.get("content") or "", m.get("tool_calls") or []
        if not calls:
            obs = env.step(ManagerAction(type="end_turn", text=content, metadata={"tokens": tok}))
            break
        for c in calls:
            fn = c["function"]
            try:
                args = fn.get("arguments") or "{}"
                args = json.loads(args) if isinstance(args, str) else args
            except ValueError:
                args = {}
            obs = env.step(ManagerAction(type="call_tool", tool_name=fn["name"], arguments=args if isinstance(args, dict) else {},
                                         metadata={"content": content, "tokens": tok}))
            msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": obs.tool_result or ""})
            tool_trace.append({"tool_name": fn["name"], "arguments": args,
                               "result": {"data": obs.tool_result, "done": obs.done, "metadata": {}, "error": obs.tool_error or None}})
            if obs.done:
                break
    return obs, msgs, tool_trace, tok


def run_candidate(c, arm, url, model, scenarios_filter, out_dir, resume, log=print, scenarios_path=None):
    driver = gepa.make_driver(c, arm, url, model)
    env = ManagerEnvironment(options=c.get("env") or {}, scenarios_path=scenarios_path)
    out = os.path.join(out_dir, f"{arm}-{c['id']}.json")
    rdir = os.path.join(out_dir, f"{arm}-{c['id']}.rollouts")
    ser = RolloutSerializer(rdir)
    done = {}
    if resume and os.path.exists(out):
        done = {r["id"]: r for r in json.load(open(out))["runs"]}
    elif os.path.exists(ser.results_path):
        os.remove(ser.results_path)
    info = {"driver_info": driver.info()}
    runs, stopped = [], None
    for sc in env.scenarios:
        if scenarios_filter and sc["id"] not in scenarios_filter:
            continue
        if sc["id"] in done:
            runs.append(done[sc["id"]])
            continue
        try:
            obs, msgs, tool_trace, tok = play(env, driver, sc["id"])
        except drivers.RateLimited as e:
            stopped = f"rate limit at {sc['id']}: {e}"
            break
        except Exception as e:  # a timeout or a dropped connection costs this scenario, not the run
            err = f"{type(e).__name__}: {e}"[:300]
            obs = env.step(ManagerAction(type="end_turn", metadata={"error": err})) if not env.episode["done"] else None
            msgs, tool_trace, tok = [], [], drivers.tokens()
        ep = env.episode
        sco = env.rubric.last_detail
        runs.append({"id": sc["id"], "score": sco, "trace": ep["trace"], "final_text": ep["res"]["final_text"],
                     "error": ep["res"]["error"], "reported_model": driver.model, "offered_tools": ep["res"]["offered_tools"],
                     "prefill": driver.prefill, **({"env_intercepts": ep["hits"]} if c.get("env") else {})})
        ser.write_episode(EpisodeRecord(
            episode_id=f"{arm}-{c['id']}-{sc['id']}", messages=msgs, reward=1.0 if sco["routing_ok"] else 0.0, done=True, tool_trace=tool_trace,
            metrics={"tokens": tok, "wall_s": sco["wall_s"]}, verify_metrics=sco, artifacts={"final_text": ep["res"]["final_text"]},
            task={"scenario_id": sc["id"]}, extra={"arm": arm, "candidate": c["id"], "model": driver.model}))
        log(f"{sc['id']}: {','.join(sco['tags'])} {sco['named']} routing={'ok' if sco['routing_ok'] else 'WRONG'} "
            f"{sco['wall_s']:.1f}s {tok['output']} out" + (f" ERROR {sco['error'][:80]}" if sco.get("error") else ""))
        with open(out, "w") as f:
            json.dump({"driver": driver.name, **info, "stopped": stopped, "runs": runs}, f, indent=1)
    with open(out, "w") as f:
        json.dump({"driver": driver.name, **info, "date": datetime.date.today().isoformat(), "stopped": stopped,
                   "runs": runs}, f, indent=1)
    ser.write_metadata({"arm": arm, "candidate": c["id"], "driver": driver.info(), "env": "manager-env",
                        "env_options": c.get("env") or {}, "stopped": stopped, "date": datetime.date.today().isoformat()})
    return runs, stopped, out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", default="local")
    ap.add_argument("--candidates")
    ap.add_argument("--id", default="base")
    ap.add_argument("--prompt")
    ap.add_argument("--env")
    ap.add_argument("--extra")
    ap.add_argument("--prefill", choices=["off", "on", "auto"])
    ap.add_argument("--only")
    ap.add_argument("--out-dir")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--scenarios")
    a = ap.parse_args(argv)
    if a.candidates:
        cands = gepa.load_candidates(a.candidates)
    else:
        cands = [{"id": a.id, "prompt": a.prompt, "env": json.loads(a.env or "{}"), "extra": json.loads(a.extra or "{}"),
                  "prefill": a.prefill or "off"}]
    out_dir = a.out_dir or DEFAULT_DIR
    os.makedirs(out_dir, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    stopped = None
    for i, c in enumerate(cands, 1):
        print(f"== candidate {c['id']} ({i}/{len(cands)})", flush=True)
        runs, stopped, out = run_candidate(c, a.arm, a.url, a.model, only, out_dir, a.resume, lambda s: print(s, flush=True),
                                           a.scenarios)
        print(f"== {c['id']}: routing {sum(1 for r in runs if r['score']['routing_ok'])}/{len(runs)} -> {out}"
              + (f"; STOPPED: {stopped}" if stopped else ""), flush=True)
        if stopped:
            break
    return 2 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
