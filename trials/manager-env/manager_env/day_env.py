"""manager-env, tier 2: a simulated working day. One episode is a Day (day.py); one turn is one arrival; the manager is a
fresh session per turn (the portfolio, which persists across the day, is its memory).

reset(day_id=... | day={...} | seed=N) -> the first arrival. step(DayAction):
  call_tool  runs a manager tool on the day's one portfolio (stub_pm.Stub, not reset between turns);
  end_turn   ends the turn on the current arrival: the arrival is scored (score.score on a scenario synthesised from the
             arrival, its label resolved at run time), the clock advances by seconds x speed, and the next arrival is
             delivered. done when the day's queue is empty.
Options: tier 1's (inline_portfolio, dedupe, search_budget, final_nudge, max_turns, tools, noop_tool, stop_after_action: per turn) and `owner_first`, `speed`.
Reward: per-arrival routing on each end_turn observation; on the final one the mean per-arrival routing. The episode terms
(owner wait, dropped loops, double writers, interruptions) are in `episode` of the final observation, unweighted.
"""
from __future__ import annotations

import copy
import json
import os
import random
import time
import uuid
from typing import Any, Optional

from fastmcp import FastMCP
from openenv.core.env_server.mcp_environment import MCPEnvironment
from openenv.core.env_server.mcp_types import CallToolAction, ListToolsAction

from . import _pm1a  # noqa: F401
import drivers  # noqa: E402
import replay  # noqa: E402
import score as S  # noqa: E402
import stub_pm  # noqa: E402

from .day import DAYS_DIR, Day, generate_day, hhmm, load_day  # noqa: E402
from .day_models import DayAction, DayObservation, DayState  # noqa: E402
from .environment import NOOP_TOOL, allowed_tool, offered_tools  # noqa: E402
from .models import ManagerAction  # noqa: E402

DEFAULT_MAX_STEPS = 10
ENV_KEYS = drivers.OpenAICompatible.ENV_KEYS + ("owner_first", "speed")
OPTIONS_VAR = "MANAGER_DAY_OPTIONS"


class _DayStub(stub_pm.Stub):
    """stub_pm.Stub with its trace in memory. `trace` is the current turn's; the portfolio is the day's."""

    def __init__(self, portfolio):
        super().__init__(portfolio, None)
        self.trace: list = []

    def log(self, rec: dict) -> None:
        self.seq += 1
        self.trace.append({"seq": self.seq, "ts": 0.0, **rec})


def _key(name: str, args: dict) -> str:
    return name + json.dumps(args, sort_keys=True, separators=(",", ":"))


class DayEnvironment(MCPEnvironment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, options: Optional[dict] = None, days_dir: Optional[str] = None, scenarios_path: Optional[str] = None,
                 fixture_path: Optional[str] = None, max_steps: Optional[int] = None):
        super().__init__(FastMCP("manager-env-day"))
        if options is None:
            options = json.loads(os.environ.get(OPTIONS_VAR) or "{}")
        self.options = dict(options)
        bad = sorted(set(self.options) - set(ENV_KEYS))
        if bad:
            raise ValueError(f"unknown env option(s) {bad}; known: {list(ENV_KEYS)}")
        self.max_steps = int(self.options.get("max_turns") or max_steps or DEFAULT_MAX_STEPS)
        self.owner_first = bool(self.options.get("owner_first", False))
        self.speed = float(self.options.get("speed", 1.0))
        self.days_dir = days_dir or DAYS_DIR
        self.scenarios, self.portfolio = replay.load_world(scenarios_path, fixture_path)
        self.day: Optional[Day] = None
        self.stub: Optional[_DayStub] = None
        self.turn: Optional[dict] = None
        self.arrival: Optional[dict] = None
        self.done = False
        self._state = DayState()

    # ---- OpenEnv surface
    def reset(self, seed: Optional[int] = None, episode_id: Optional[str] = None, day_id: Optional[str] = None,
              day: Optional[dict] = None, **kwargs: Any) -> DayObservation:
        """day_id (a file in days/, or a path), or day (the spec dict), or seed (a generated day), else a random seed."""
        if day is not None:
            spec = day
        elif day_id is not None:
            spec = load_day(day_id, self.days_dir)
        else:
            seed = int(seed) if seed is not None else random.randrange(10 ** 6)
            spec = generate_day(seed, scenarios=self.scenarios)
        self.stub = _DayStub(copy.deepcopy(self.portfolio))
        self.day = Day(spec, self.stub.p, owner_first=self.owner_first, speed=self.speed)
        self.done = False
        self._state = DayState(episode_id=episode_id or str(uuid.uuid4()), step_count=0, day_id=self.day.id)
        return self._deliver(None)

    def step(self, action, timeout_s: Optional[float] = None, **kwargs: Any) -> DayObservation:
        return self._step_impl(self._coerce(action))

    async def step_async(self, action, timeout_s: Optional[float] = None, **kwargs: Any) -> DayObservation:
        return self._step_impl(self._coerce(action))

    @property
    def state(self) -> DayState:
        return self._state

    def get_metadata(self):
        from openenv.core.env_server.types import EnvironmentMetadata
        return EnvironmentMetadata(name="manager-env-day", version="0.1.0",
                                   description="PM-1a tier 2: a simulated day of storylines over a persistent portfolio; "
                                               "reward is the mean per-arrival routing, episode terms reported.")

    # ---- internals
    @staticmethod
    def _coerce(action) -> DayAction:
        if isinstance(action, DayAction):
            return action
        if isinstance(action, ManagerAction):
            return DayAction(**action.model_dump())
        if isinstance(action, CallToolAction):
            return DayAction(type="call_tool", tool_name=action.tool_name, arguments=action.arguments, metadata=action.metadata)
        if isinstance(action, ListToolsAction):
            return DayAction(type="list_tools")
        raise TypeError(f"not a manager action: {type(action).__name__}")

    def _nudge(self):
        t = self.turn
        if self.options.get("final_nudge") and self.max_steps > 1 and t and t["steps"] == self.max_steps - 1:
            return drivers.OpenAICompatible.FINAL_NUDGE
        return None

    def _obs(self, tools=False, tool_result=None, tool_error=False, nudge=None, message=None, **kw) -> DayObservation:
        d, a, t = self.day, self.arrival, self.turn
        return DayObservation(
            scenario_id=a["sid_full"] if a else "", message=message if message is not None else "",
            tools=offered_tools(self.options) if tools else [], tool_result=tool_result, tool_error=tool_error, nudge=nudge,
            step=t["steps"] if t else 0, max_steps=self.max_steps, done=False, reward=None, day_id=d.id,
            arrival_index=a["n"] if a else 0, source=a["source"] if a else "", kind=a["kind"] if a else "",
            clock_s=d.clock, clock=hhmm(d.clock), queue_len=len(d.pending), **kw)

    def _deliver(self, finished: Optional[dict]) -> DayObservation:
        """Deliver the next arrival (or end the day). `finished` is the record of the arrival just scored."""
        d = self.day
        a = d.next_arrival()
        extra = {}
        if finished:
            extra = {"arrival_score": finished["score"], "arrival_record": finished}
        if a is None:
            self.arrival, self.turn, self.done = None, None, True
            ep = d.episode()
            obs = self._obs(episode=ep, **extra)
            obs.done = True
            obs.reward = float(ep["routing"] or 0.0)
            obs.metadata = {"episode": ep, **({"arrival_score": finished["score"]} if finished else {})}
            self._state.done = True
            return obs
        self.arrival = a
        self.turn = {"steps": 0, "attempts": [], "seen": set(), "searches": 0, "hits": {"dedupe": 0, "search_budget": 0},
                     "content": "", "tokens": drivers.tokens(), "error": None, "t0": time.monotonic(), "calls": []}
        self.stub.trace = []
        msg = d.message(a)
        if self.options.get("inline_portfolio"):
            msg += "\n\nCurrent portfolio (what pm_portfolio returns):\n" + json.dumps(self.stub.p)
        self._state.arrival_id = a["sid_full"]
        self._state.clock_s = d.clock
        obs = self._obs(tools=True, message=msg, nudge=self._nudge(), **extra)
        if finished:
            obs.reward = 1.0 if finished["routing_ok"] else 0.0
            obs.metadata = {"arrival_score": finished["score"]}
        return obs

    def _step_impl(self, action: DayAction) -> DayObservation:
        if self.day is None:
            raise RuntimeError("reset() first")
        if action.type == "list_tools":
            return self._obs(tools=True, nudge=None if self.done else self._nudge())
        if self.done:
            raise RuntimeError("the day is over; reset()")
        t = self.turn
        md = action.metadata or {}
        if md.get("content"):
            t["content"] = md["content"]
        if md.get("tokens"):
            t["tokens"] = md["tokens"]
        if md.get("error"):
            t["error"] = md["error"]
        t["steps"] += 1
        self._state.step_count += 1
        if action.type == "end_turn":
            if action.text.strip():
                t["content"] = action.text
            return self._end_turn(action.seconds)
        name, args = action.tool_name, action.arguments if isinstance(action.arguments, dict) else {}
        opts, stub = self.options, self.stub
        if opts.get("noop_tool") and name == NOOP_TOOL["name"]:
            return self._end_turn(md.get("t"))
        stop = False
        t["attempts"].append(name)
        key = _key(name, args)
        n_before = len(stub.trace)
        if opts.get("dedupe") and key in t["seen"]:
            t["hits"]["dedupe"] += 1
            result, err = drivers.OpenAICompatible.DEDUPE_MSG, False
        elif name == "kernel_search" and opts.get("search_budget") is not None and t["searches"] >= int(opts["search_budget"]):
            t["hits"]["search_budget"] += 1
            result, err = drivers.OpenAICompatible.SEARCH_MSG, False
        else:
            if name == "kernel_search":
                t["searches"] += 1
            if allowed_tool(opts, name):
                result, err = stub.call(name, args)
                stop = bool(opts.get("stop_after_action")) and not err and name in drivers.OpenAICompatible.ACTIONS
            else:
                result, err = f"no such tool: {name}", True
        t["seen"].add(key)
        if len(stub.trace) > n_before:
            t["calls"].append((stub.trace[-1], md.get("t"), time.monotonic() - t["t0"]))
        if stop:
            return self._end_turn(md.get("t"))
        if t["steps"] >= self.max_steps:
            t["error"] = t["error"] or f"no final answer in {self.max_steps} turns"
            return self._end_turn(None)
        return self._obs(tool_result=result, tool_error=err, nudge=self._nudge())

    def _end_turn(self, seconds: Optional[float]) -> DayObservation:
        d, a, t, stub = self.day, self.arrival, self.turn, self.stub
        explicit = seconds is not None
        secs = float(seconds) if explicit else time.monotonic() - t["t0"]
        for entry, t_md, t_wall in t["calls"]:
            entry["t"] = t_md if t_md is not None else (None if explicit else t_wall)
        trace = stub.trace
        info = d.close_turn(a, trace, t["content"], secs)
        for entry in trace:  # the stub's timestamps become simulated clock seconds
            entry["ts"] = entry.pop("sim", info["end"])
            entry.pop("t", None)
        res = {"final_text": t["content"], "launch_ts": info["start"], "wall_s": secs, "tokens": t["tokens"],
               "offered_tools": list(stub_pm.NAMES), "attempts": t["attempts"], "error": t["error"], "model": "env"}
        score = S.score(d.scenario(a), stub.p, trace, res)
        rec = d.add_record(a, info, score, final_text=t["content"], error=t["error"])
        rec["trace"] = copy.deepcopy(trace)
        rec["seconds"] = secs
        rec["tokens"] = t["tokens"]
        if self.options:
            rec["env_intercepts"] = t["hits"]
        return self._deliver(rec)

    def close(self) -> None:
        super().close()
