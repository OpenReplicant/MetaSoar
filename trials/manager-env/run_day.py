"""Tier 2 rollouts: an OpenAI-compatible chat endpoint driven through manager-env's simulated days.

    python3 run_day.py --arm inkling --url http://127.0.0.1:8081 --model inkling [--candidates cands.json] [--days train-00,train-03]
        [--days-dir DIR] [--out-dir DIR] [--resume] [--owner-first] [--speed 1.0] [--env '{"dedupe": true}'] [--id base]
        [--prompt prompts/c0.md] [--extra JSON] [--prefill auto]

Like run.py, per day: every arrival is one turn and a fresh model session (system prompt, this arrival's message, the nine
tools on the day's one portfolio). The turn's measured wall seconds (model calls only; the tools are instant) go to the
environment as `seconds` on end_turn, and each tool call carries its measured offset as metadata["t"], so the clock, the owner
wait and the queue come from what the model really took. cands.json is gepa.py's; the request is drivers.OpenAICompatible.turn.
For each candidate it writes, in DIR (default trials/manager-eval/pm1a/results/gepa-day):
    <arm>-<id>.days.json     per day: the per-arrival scores (score.score's dict, trace, final text, wait) and the episode metrics
    <arm>-<id>.rollouts/     OpenEnv harness records, one per arrival turn (a fresh session each): results.jsonl (`messages` form
                             for TRL's SFTTrainer, reward = that arrival's routing, tool_trace, the score dict as verify_metrics)
                             and metadata.json
The episode terms (owner wait, dropped loops, double writers, interruptions) are reported, not weighted into the reward.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from manager_env import DayAction, DayEnvironment, _pm1a  # noqa: E402
from manager_env.day import DAYS_DIR  # noqa: E402
import drivers  # noqa: E402
import gepa  # noqa: E402

from openenv.core.harness.collect import EpisodeRecord, RolloutSerializer  # noqa: E402

DEFAULT_DIR = os.path.join(_pm1a.PM1A_DIR, "results", "gepa-day")


def play_turn(env, driver, obs, log=print):
    """One arrival: a fresh session. Returns (the observation after end_turn, messages, tool_trace, usage, seconds)."""
    t0 = time.monotonic()
    msgs = [{"role": "system", "content": driver.prompt}, {"role": "user", "content": obs.message}]
    tool_trace, tok = [], drivers.tokens()
    while True:
        if obs.nudge:
            msgs.append({"role": "user", "content": obs.nudge})
        r = driver.turn(msgs)
        u = r.get("usage") or {}
        tok = drivers.tokens(tok["input"] + u.get("prompt_tokens", 0), tok["output"] + u.get("completion_tokens", 0),
                             turns=tok["turns"] + 1)
        m = r["choices"][0]["message"]
        msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls") and v is not None})
        content, calls = m.get("content") or "", m.get("tool_calls") or []
        now = time.monotonic() - t0
        if not calls:
            return env.step(DayAction(type="end_turn", text=content, seconds=now, metadata={"tokens": tok})), msgs, tool_trace, tok, now
        for c in calls:
            fn = c["function"]
            try:
                args = fn.get("arguments") or "{}"
                args = json.loads(args) if isinstance(args, str) else args
            except ValueError:
                args = {}
            obs = env.step(DayAction(type="call_tool", tool_name=fn["name"], arguments=args if isinstance(args, dict) else {},
                                     metadata={"content": content, "tokens": tok, "t": now}))
            msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": obs.tool_result or ""})
            tool_trace.append({"tool_name": fn["name"], "arguments": args,
                               "result": {"data": obs.tool_result, "done": False, "metadata": {}, "error": obs.tool_error or None}})
            if obs.arrival_record is not None:  # the step limit ended the turn inside the tool call
                return obs, msgs, tool_trace, tok, now


def run_day(env, driver, day_id, ser, arm, cid, log=print):
    obs = env.reset(day_id=day_id)
    arrivals = []
    while not obs.done:
        turn_id = f"{arm}-{cid}-{day_id}-{obs.arrival_index:02d}"
        msg = obs.message
        t0 = time.monotonic()
        try:
            nxt, msgs, tool_trace, tok, secs = play_turn(env, driver, obs, log)
        except drivers.RateLimited:
            raise
        except Exception as e:  # a timeout or a dropped connection costs this turn, not the day
            err = f"{type(e).__name__}: {e}"[:300]
            secs = time.monotonic() - t0
            nxt = env.step(DayAction(type="end_turn", seconds=secs, metadata={"error": err}))
            msgs, tool_trace, tok = [], [], drivers.tokens()
        rec = nxt.arrival_record
        sco = rec["score"]
        arrivals.append({k: rec[k] for k in ("id", "n", "tag", "source", "kind", "at", "delivered_at", "queue_delay_s", "started_at",
                                              "ended_at", "clock", "expected", "wait_s", "unanswered", "interruptions",
                                              "routing_ok", "score", "final_text", "error", "trace", "seconds", "tokens")
                         if k in rec} | ({"env_intercepts": rec["env_intercepts"]} if "env_intercepts" in rec else {}))
        ser.write_episode(EpisodeRecord(
            episode_id=turn_id, messages=msgs, reward=1.0 if sco["routing_ok"] else 0.0, done=True, tool_trace=tool_trace,
            metrics={"tokens": tok, "wall_s": secs, "queue_delay_s": rec["queue_delay_s"], "wait_s": rec["wait_s"]},
            verify_metrics=sco, artifacts={"final_text": rec["final_text"], "message": msg},
            task={"day": day_id, "arrival": rec["id"], "tag": rec["tag"]},
            extra={"arm": arm, "candidate": cid, "model": driver.model}))
        log(f"{day_id} {rec['clock']} {rec['tag']}: {','.join(sco['tags'])} {sco['named']} "
            f"routing={'ok' if sco['routing_ok'] else 'WRONG'} {secs:.1f}s" + (f" ERROR {rec['error'][:80]}" if rec["error"] else ""))
        obs = nxt
    return {"id": day_id, "arrivals": arrivals, "episode": obs.episode, "reward": obs.reward}


def run_candidate(c, arm, url, model, day_ids, days_dir, out_dir, resume, owner_first=False, speed=1.0, log=print):
    driver = gepa.make_driver(c, arm, url, model)
    env = DayEnvironment(options={**(c.get("env") or {}), "owner_first": owner_first, "speed": speed}, days_dir=days_dir)
    out = os.path.join(out_dir, f"{arm}-{c['id']}.days.json")
    ser = RolloutSerializer(os.path.join(out_dir, f"{arm}-{c['id']}.rollouts"))
    done = {}
    if resume and os.path.exists(out):
        done = {d["id"]: d for d in json.load(open(out))["days"]}
    elif os.path.exists(ser.results_path):
        os.remove(ser.results_path)
    info = {"driver_info": driver.info(), "owner_first": owner_first, "speed": speed}
    days, stopped = [], None

    def save():
        with open(out, "w") as f:
            json.dump({"driver": driver.name, **info, "date": datetime.date.today().isoformat(), "stopped": stopped,
                       "days": days}, f, indent=1)

    for day_id in day_ids:
        if day_id in done:
            days.append(done[day_id])
            continue
        try:
            days.append(run_day(env, driver, day_id, ser, arm, c["id"], log))
        except drivers.RateLimited as e:
            stopped = f"rate limit in {day_id}: {e}"
            break
        save()
    save()
    ser.write_metadata({"arm": arm, "candidate": c["id"], "driver": driver.info(), "env": "manager-env-day",
                        "env_options": env.options, "stopped": stopped, "date": datetime.date.today().isoformat()})
    return days, stopped, out


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
    ap.add_argument("--days", help="comma-separated day ids (files in --days-dir); default: every train-*.json")
    ap.add_argument("--days-dir")
    ap.add_argument("--out-dir")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--owner-first", action="store_true")
    ap.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args(argv)
    if a.candidates:
        cands = gepa.load_candidates(a.candidates)
    else:
        cands = [{"id": a.id, "prompt": a.prompt, "env": json.loads(a.env or "{}"), "extra": json.loads(a.extra or "{}"),
                  "prefill": a.prefill or "off"}]
    days_dir = a.days_dir or DAYS_DIR
    day_ids = a.days.split(",") if a.days else sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(days_dir, "train-*.json")))
    out_dir = a.out_dir or DEFAULT_DIR
    os.makedirs(out_dir, exist_ok=True)
    stopped = None
    for i, c in enumerate(cands, 1):
        print(f"== candidate {c['id']} ({i}/{len(cands)})", flush=True)
        days, stopped, out = run_candidate(c, a.arm, a.url, a.model, day_ids, days_dir, out_dir, a.resume, a.owner_first, a.speed,
                                           lambda s: print(s, flush=True))
        for d in days:
            e = d["episode"]
            print(f"== {c['id']} {d['id']}: routing {e['routing']:.3f} over {e['arrivals']}, owner wait median "
                  f"{e['owner_wait']['median_s']} p90 {e['owner_wait']['p90_s']}, dropped loops {e['dropped_loops']['count']}, "
                  f"double writers {e['double_writers']['count']}, interruptions {e['interruptions']}", flush=True)
        print(f"-> {out}" + (f"; STOPPED: {stopped}" if stopped else ""), flush=True)
        if stopped:
            break
    return 2 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
