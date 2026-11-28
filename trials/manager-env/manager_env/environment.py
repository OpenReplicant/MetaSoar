"""manager-env, tier 1: one PM-1a scenario per episode, each step one manager tool call or the end of the turn.

Why MCPEnvironment: it is OpenEnv's base for tool environments, and gives the standard action and tool-list contract
(CallToolAction, ListToolsAction) and the HTTP, WebSocket and MCP wiring. It does not fit as is: its tools are Python
functions on a FastMCP server made once, and ours are the nine JSON-schema tools of stub_pm, run on a portfolio that is
fresh for every episode. So the environment hands the base an empty FastMCP server (only to satisfy the constructor) and
takes over step(): the tool list is stub_pm.TOOLS word for word, and a call runs on the episode's own stub_pm.Stub.
`ManagerAction` is one pydantic model for the three moves (call_tool, end_turn, list_tools); CallToolAction and
ListToolsAction are accepted too and turned into it.
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

from . import _pm1a  # noqa: F401  (puts pm1a on sys.path)
import drivers  # noqa: E402
import replay  # noqa: E402
import score as S  # noqa: E402
import stub_pm  # noqa: E402

from .models import ManagerAction, ManagerObservation, ManagerState  # noqa: E402
from .rubric import RoutingRubric  # noqa: E402

DEFAULT_MAX_STEPS = 10
ENV_KEYS = drivers.OpenAICompatible.ENV_KEYS  # the same option names as the driver's env dict
OPTIONS_VAR = "MANAGER_ENV_OPTIONS"  # JSON; how the served app gets its options


class _MemStub(stub_pm.Stub):
    """stub_pm.Stub with its trace kept in memory, not in a file. Everything else is the original."""

    def __init__(self, portfolio):
        super().__init__(portfolio, None)
        self.trace: list = []

    def log(self, rec: dict) -> None:
        self.seq += 1
        self.trace.append({"seq": self.seq, "ts": round(time.time(), 3), **rec})


NOOP_TOOL = {"name": drivers.OpenAICompatible.NOOP_TOOL["function"]["name"],
             "description": drivers.OpenAICompatible.NOOP_TOOL["function"]["description"],
             "inputSchema": drivers.OpenAICompatible.NOOP_TOOL["function"]["parameters"]}


def offered_tools(options: dict) -> list:
    """The tool list the observations carry: stub_pm.TOOLS filtered by `tools`, plus NOOP_TOOL if `noop_tool` (as the driver
    puts it in its requests)."""
    want = options.get("tools")
    out = [t for t in copy.deepcopy(stub_pm.TOOLS) if want is None or t["name"] in want]
    if options.get("noop_tool"):
        out.append(copy.deepcopy(NOOP_TOOL))
    return out


def allowed_tool(options: dict, name: str) -> bool:
    return name in stub_pm.NAMES and (options.get("tools") is None or name in options["tools"])


def _key(name: str, args: dict) -> str:
    return name + json.dumps(args, sort_keys=True, separators=(",", ":"))


class ManagerEnvironment(MCPEnvironment):
    """options (drivers.OpenAICompatible's env dict; the environment owns them):
      inline_portfolio  the opening message gets "Current portfolio (what pm_portfolio returns):\\n<json>" appended;
      dedupe            an exact repeat of a call (same tool, same arguments) is answered with DEDUPE_MSG, not run;
      search_budget     kernel_search calls past this many are answered with SEARCH_MSG, not run;
      final_nudge       the observation before the last allowed step carries FINAL_NUDGE in `nudge`;
      tools             (list) only these of the stub's tools are offered; a call to another is answered "no such tool: <name>";
      noop_tool         NOOP_TOOL (pm_nothing) is also offered; calling it ends the episode as end_turn with empty text
                        (not run, not in attempts);
      stop_after_action the episode ends after the first successful call of drivers.OpenAICompatible.ACTIONS;
      max_turns         the step limit (alias of max_steps; default 10);
      max_tokens        accepted and ignored here: it belongs to the model call.
    The messages are drivers.OpenAICompatible's, so the two cannot drift apart."""

    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, options: Optional[dict] = None, scenarios_path: Optional[str] = None,
                 fixture_path: Optional[str] = None, max_steps: Optional[int] = None):
        super().__init__(FastMCP("manager-env"))
        if options is None:
            options = json.loads(os.environ.get(OPTIONS_VAR) or "{}")
        self.options = dict(options)
        bad = sorted(set(self.options) - set(ENV_KEYS))
        if bad:
            raise ValueError(f"unknown env option(s) {bad}; known: {list(ENV_KEYS)}")
        self.max_steps = int(self.options.get("max_turns") or max_steps or DEFAULT_MAX_STEPS)
        self.scenarios, self.portfolio = replay.load_world(scenarios_path, fixture_path)
        self.by_id = {s["id"]: s for s in self.scenarios}
        self.rubric = RoutingRubric(self)
        self.episode: Optional[dict] = None
        self._state = ManagerState()

    # ---- OpenEnv surface
    def reset(self, seed: Optional[int] = None, episode_id: Optional[str] = None, scenario_id: Optional[str] = None,
              **kwargs: Any) -> ManagerObservation:
        """scenario_id picks the scenario; else seed picks scenarios[seed % n]; else one at random."""
        if scenario_id is not None:
            if scenario_id not in self.by_id:
                raise ValueError(f"unknown scenario {scenario_id!r}; known: {', '.join(self.by_id)}")
            sc = self.by_id[scenario_id]
        elif seed is not None:
            sc = self.scenarios[int(seed) % len(self.scenarios)]
        else:
            sc = random.choice(self.scenarios)
        self._reset_rubric()
        pf = replay.fresh(self.portfolio, sc)
        stub = _MemStub(pf)
        message = S.message_for(sc)
        if self.options.get("inline_portfolio"):
            message += "\n\nCurrent portfolio (what pm_portfolio returns):\n" + json.dumps(stub.p)
        t0 = time.time()
        self.episode = {"scenario": sc, "portfolio": pf, "stub": stub, "message": message, "t0": t0, "steps": 0,
                        "attempts": [], "seen": set(), "searches": 0, "hits": {"dedupe": 0, "search_budget": 0},
                        "content": "", "tokens": drivers.tokens(), "error": None, "done": False,
                        "trace": stub.trace, "res": None}
        self._state = ManagerState(episode_id=episode_id or str(uuid.uuid4()), step_count=0, scenario_id=sc["id"])
        return self._obs(tools=True, nudge=self._nudge())

    def step(self, action, timeout_s: Optional[float] = None, **kwargs: Any) -> ManagerObservation:
        return self._step_impl(self._coerce(action))

    async def step_async(self, action, timeout_s: Optional[float] = None, **kwargs: Any) -> ManagerObservation:
        return self._step_impl(self._coerce(action))

    def _step_impl(self, action, timeout_s: Optional[float] = None, **kwargs: Any) -> ManagerObservation:
        ep = self.episode
        if ep is None:
            raise RuntimeError("reset() first")
        if action.type == "list_tools":
            return self._obs(tools=True, nudge=self._nudge())
        if ep["done"]:
            raise RuntimeError("the episode is over; reset()")
        md = action.metadata or {}
        if md.get("content"):
            ep["content"] = md["content"]
        if md.get("tokens"):
            ep["tokens"] = md["tokens"]
        if md.get("error"):
            ep["error"] = md["error"]
        ep["steps"] += 1
        self._state.step_count = ep["steps"]
        if action.type == "end_turn":
            if action.text.strip():
                ep["content"] = action.text
            return self._finish(action)
        # a tool call
        name, args = action.tool_name, action.arguments if isinstance(action.arguments, dict) else {}
        opts, stub = self.options, ep["stub"]
        if opts.get("noop_tool") and name == NOOP_TOOL["name"]:
            return self._finish(action)
        stop = False
        ep["attempts"].append(name)
        key = _key(name, args)
        if opts.get("dedupe") and key in ep["seen"]:
            ep["hits"]["dedupe"] += 1
            result, err = drivers.OpenAICompatible.DEDUPE_MSG, False
        elif (name == "kernel_search" and opts.get("search_budget") is not None
              and ep["searches"] >= int(opts["search_budget"])):
            ep["hits"]["search_budget"] += 1
            result, err = drivers.OpenAICompatible.SEARCH_MSG, False
        else:
            if name == "kernel_search":
                ep["searches"] += 1
            if allowed_tool(opts, name):
                result, err = stub.call(name, args)
                stop = bool(opts.get("stop_after_action")) and not err and name in drivers.OpenAICompatible.ACTIONS
            else:
                result, err = f"no such tool: {name}", True
        ep["seen"].add(key)
        if stop:
            return self._finish(action, tool_result=result, tool_error=err)
        if ep["steps"] >= self.max_steps:
            ep["error"] = ep["error"] or f"no final answer in {self.max_steps} turns"
            return self._finish(action, tool_result=result, tool_error=err)
        return self._obs(tool_result=result, tool_error=err, nudge=self._nudge())

    @property
    def state(self) -> ManagerState:
        return self._state

    def get_metadata(self):
        from openenv.core.env_server.types import EnvironmentMetadata
        return EnvironmentMetadata(name="manager-env", version="0.1.0",
                                   description="PM-1a, tier 1: one message or event to a manager with nine tools; "
                                               "reward is 1.0 when score.score marks the routing right.")

    # ---- internals
    @staticmethod
    def _coerce(action) -> ManagerAction:
        if isinstance(action, ManagerAction):
            return action
        if isinstance(action, CallToolAction):
            return ManagerAction(type="call_tool", tool_name=action.tool_name, arguments=action.arguments,
                                 metadata=action.metadata)
        if isinstance(action, ListToolsAction):
            return ManagerAction(type="list_tools")
        raise TypeError(f"not a manager action: {type(action).__name__}")

    def _nudge(self) -> Optional[str]:
        ep = self.episode
        if (self.options.get("final_nudge") and self.max_steps > 1 and ep and not ep["done"]
                and ep["steps"] == self.max_steps - 1):
            return drivers.OpenAICompatible.FINAL_NUDGE
        return None

    def _obs(self, tools=False, tool_result=None, tool_error=False, nudge=None, **kw) -> ManagerObservation:
        ep = self.episode
        return ManagerObservation(scenario_id=ep["scenario"]["id"], message=ep["message"] if ep["steps"] == 0 else "",
                                  tools=offered_tools(self.options) if tools else [], tool_result=tool_result,
                                  tool_error=tool_error, nudge=nudge, step=ep["steps"], max_steps=self.max_steps,
                                  done=False, reward=None, **kw)

    def _finish(self, action, tool_result=None, tool_error=False) -> ManagerObservation:
        ep = self.episode
        ep["done"] = True
        now = time.time()
        ep["res"] = {"final_text": ep["content"], "launch_ts": ep["t0"], "wall_s": now - ep["t0"], "tokens": ep["tokens"],
                     "offered_tools": list(stub_pm.NAMES), "attempts": ep["attempts"], "error": ep["error"], "model": "env"}
        if self.options:
            ep["res"]["env_intercepts"] = ep["hits"]
        obs = self._obs(tool_result=tool_result, tool_error=tool_error)
        obs.done = True
        obs.reward = float(self._apply_rubric(action, obs))
        obs.metadata = {"score": self.rubric.last_detail, "final_text": ep["content"], "error": ep["error"],
                        **({"env_intercepts": ep["hits"]} if self.options else {})}
        obs.score = self.rubric.last_detail
        self._state.done = True
        return obs

    def close(self) -> None:
        super().close()
