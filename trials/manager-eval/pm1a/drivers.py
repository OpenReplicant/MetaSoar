"""PM-1a's drivers: one interface, three ways to put a message to a manager (docs/manager-agent.md, section 8).

    driver.run(text, portfolio, trace_path) -> dict
        {"final_text", "launch_ts", "wall_s", "tokens": {...}, "offered_tools": [...], "attempts": [tool names the
         model called, as it named them], "error": str|None, "model": str}

The tools' calls themselves are written to `trace_path` (JSONL) by the stub (stub_pm.py), in another process for
`claude-code`, in this one for `openai-compatible`; `choice` writes one synthetic call. A rate limit raises
RateLimited so the run can stop and report.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import stub_pm

HERE = os.path.dirname(os.path.abspath(__file__))
ACTION_TOOLS = {"start": "pm_worker_start", "message": "pm_worker_message", "stop": "pm_worker_stop",
                "decision": "pm_decision_open", "ask": "desktop_ask", "answer": "desktop_say"}


class RateLimited(Exception):
    pass


def tokens(inp=0, out=0, cache_read=0, cache_write=0, cost=0.0, turns=0) -> dict:
    return {"input": inp, "output": out, "cache_read": cache_read, "cache_write": cache_write,
            "total_input": inp + cache_read + cache_write, "cost_usd": round(cost, 5), "turns": turns}


class Fake:
    """For tests: `script` maps a message to a list of (tool, arguments) calls, run against the real stub."""

    name = "fake"

    def __init__(self, script):
        self.script = script

    def run(self, text, portfolio, trace_path):
        t0 = time.time()
        stub = stub_pm.Stub(portfolio, trace_path)
        attempts = []
        for name, args in self.script(text):
            attempts.append(name)
            if name in stub_pm.NAMES:
                stub.call(name, args)
        return {"final_text": "", "launch_ts": t0, "wall_s": time.time() - t0, "tokens": tokens(turns=1),
                "offered_tools": list(stub_pm.NAMES), "attempts": attempts, "error": None, "model": "fake"}


def openai_tools():
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]}}
            for t in stub_pm.TOOLS]


def post(url, body, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(str(e))
        raise


# MetaSoar trials/handler-ladder/parse.py EMPTY_THINKING: Inkling's chat template with its thinking closed before it starts
# (no request switch stops its thinking: 401 of 450 replies ran out inside it).
EMPTY_THINKING = "<|message_model|><|content_thinking|><|end_message|><|message_model|><|content_text|>"


class OpenAICompatible:
    """A tool-calling loop over a llama.cpp server's /v1/chat/completions with the same tool schemas. `extra` is merged
    into the request (e.g. {"chat_template_kwargs": {"enable_thinking": false}}). `prefill` closes the model's thinking
    before it starts, by ending the messages with an assistant message of EMPTY_THINKING (llama.cpp continues it):
    "off", "on", or "auto" (plain first; when a turn comes back with no tool call and no text, as when the budget went
    on thinking, switch to the prefill for the rest of the run, sticky across scenarios). `mode_log` records the switch.

    `env` (default {}: nothing changes) shapes the environment around the model, for prompt/environment optimisation:
      inline_portfolio (bool)  the first user message gets "Current portfolio (what pm_portfolio returns):\n<json>" appended
                               (not a traced call);
      dedupe (bool)            an exact repeat (same tool, same arguments as canonical JSON) within a run is not sent to the
                               stub; the model gets DEDUPE_MSG;
      search_budget (int|None) kernel_search calls after this many in a run are not sent to the stub; SEARCH_MSG instead;
      final_nudge (bool)       before the last allowed turn, a user message FINAL_NUDGE is appended;
      max_turns, max_tokens    override the arguments of the same name;
      tools (list|None)        offer only these of the stub's tools (a call to another gets "no such tool");
      noop_tool (bool)         also offer NOOP_TOOL: calling it ends the turn with nothing done and nobody told (not traced);
      stop_after_action (bool) end the turn after the first successful start, message, stop, decision, ask or say.
    The result's "env_intercepts" counts the calls dedupe and search_budget answered themselves (present only when env is set)."""

    ENV_KEYS = ("inline_portfolio", "dedupe", "search_budget", "final_nudge", "max_turns", "max_tokens", "tools",
                "noop_tool", "stop_after_action")
    NOOP_TOOL = {"type": "function", "function": {"name": "pm_nothing", "description":
                 "Do nothing: this message or event needs no action and nobody is told (a progress report, a usage limit, "
                 "a stall the person asked for).", "parameters": {"type": "object", "properties": {}}}}
    ACTIONS = {"pm_worker_start", "pm_worker_message", "pm_worker_stop", "pm_decision_open", "desktop_ask", "desktop_say"}
    DEDUPE_MSG = "(You already made this exact call; its result is above. Decide and act now.)"
    SEARCH_MSG = ("(Search budget spent. Act on what you have; if the portfolio and kernel do not hold the answer, "
                  "start a worker or say you do not know.)")
    FINAL_NUDGE = "Last turn: make your decision now with one tool call, or reply in plain text."

    def __init__(self, url, model="local", prompt_file=None, extra=None, max_turns=10, timeout=900, name=None,
                 prefill="off", max_tokens=2048, env=None):
        self.name = name or f"openai-compatible:{model}"
        self.env = dict(env or {})
        bad = sorted(set(self.env) - set(self.ENV_KEYS))
        if bad:
            raise ValueError(f"unknown env option(s) {bad}; known: {list(self.ENV_KEYS)}")
        max_turns = int(self.env.get("max_turns") or max_turns)
        max_tokens = int(self.env.get("max_tokens") or max_tokens)
        self.url, self.model, self.extra, self.max_turns, self.timeout = url.rstrip("/"), model, extra or {}, max_turns, timeout
        self.prefill, self.max_tokens, self.mode_log = prefill, max_tokens, []
        self.prompt_file = os.path.abspath(prompt_file or os.path.join(HERE, "manager.md"))
        with open(self.prompt_file, "rb") as f:
            raw = f.read()
        self.prompt = raw.decode()
        self.prompt_sha256 = hashlib.sha256(raw).hexdigest()

    def info(self):
        return {"env": self.env, "prompt": self.prompt_file, "prompt_sha256": self.prompt_sha256, "url": self.url,
                "model": self.model, "extra": self.extra, "prefill": self.prefill, "max_turns": self.max_turns,
                "max_tokens": self.max_tokens}

    def turn(self, msgs):
        pre = self.prefill == "on"
        tools = [x for x in openai_tools() if self.env.get("tools") is None or x["function"]["name"] in self.env["tools"]]
        if self.env.get("noop_tool"):
            tools.append(self.NOOP_TOOL)
        body = {"model": self.model, "tools": tools, "temperature": 0, "max_tokens": self.max_tokens, **self.extra,
                "messages": msgs + ([{"role": "assistant", "content": EMPTY_THINKING}] if pre else [])}
        r = post(self.url + "/v1/chat/completions", body, self.timeout)
        m = r["choices"][0]["message"]
        if self.prefill == "auto" and not m.get("tool_calls") and not (m.get("content") or "").strip():
            self.prefill = "on"
            self.mode_log.append("switched to the empty-thinking prefill after an empty turn")
            return self.turn(msgs)
        return r

    def run(self, text, portfolio, trace_path):
        stub = stub_pm.Stub(portfolio, trace_path)
        env = self.env
        first = text
        if env.get("inline_portfolio"):
            first += "\n\nCurrent portfolio (what pm_portfolio returns):\n" + json.dumps(stub.p)
        msgs = [{"role": "system", "content": self.prompt}, {"role": "user", "content": first}]
        tok, attempts, final, error, t0 = tokens(), [], "", None, time.time()
        seen, searches, hits = set(), 0, {"dedupe": 0, "search_budget": 0}
        for turn_no in range(self.max_turns):
            if env.get("final_nudge") and self.max_turns > 1 and turn_no == self.max_turns - 1:
                msgs.append({"role": "user", "content": self.FINAL_NUDGE})
            r = self.turn(msgs)
            u = r.get("usage") or {}
            tok = tokens(tok["input"] + u.get("prompt_tokens", 0), tok["output"] + u.get("completion_tokens", 0),
                         turns=tok["turns"] + 1)
            m = r["choices"][0]["message"]
            msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls") and v is not None})
            final = m.get("content") or final
            calls = m.get("tool_calls") or []
            if not calls:
                break
            done = False
            for c in calls:
                fn = c["function"]
                try:
                    args = fn.get("arguments") or "{}"
                    args = json.loads(args) if isinstance(args, str) else args
                except ValueError:
                    args = {}
                if env.get("noop_tool") and fn["name"] == "pm_nothing":
                    done = True
                    break
                attempts.append(fn["name"])
                key = fn["name"] + json.dumps(args, sort_keys=True, separators=(",", ":"))
                if env.get("dedupe") and key in seen:
                    hits["dedupe"] += 1
                    res = self.DEDUPE_MSG
                elif (fn["name"] == "kernel_search" and env.get("search_budget") is not None
                      and searches >= int(env["search_budget"])):
                    hits["search_budget"] += 1
                    res = self.SEARCH_MSG
                else:
                    if fn["name"] == "kernel_search":
                        searches += 1
                    allowed = fn["name"] in stub_pm.NAMES and (env.get("tools") is None or fn["name"] in env["tools"])
                    if allowed:
                        res, err = stub.call(fn["name"], args)
                        if env.get("stop_after_action") and not err and fn["name"] in self.ACTIONS:
                            done = True
                    else:
                        res = f"no such tool: {fn['name']}"
                seen.add(key)
                msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": res})
                if done:
                    break
            if done:
                break
        else:
            error = f"no final answer in {self.max_turns} turns"
        out = {"final_text": final, "launch_ts": t0, "wall_s": time.time() - t0, "tokens": tok,
               "offered_tools": list(stub_pm.NAMES), "attempts": attempts, "error": error, "model": self.model,
               "prefill": self.prefill}
        if env:
            out["env_intercepts"] = hits
        return out


class Choice:
    """d1-2B's /v1/systemone for the routing decision only (MetaSoar trials/handler-ladder/stream_v3.py choose_d1):
    two choice questions, the project and the action. One synthetic call is written to the trace so the scorer treats
    it as any other arm; it has no brief, so brief quality is not scored."""

    def __init__(self, url="http://127.0.0.1:8083"):
        self.name = "choice:d1"
        self.url = url.rstrip("/")

    def ask(self, question, crit, instructions):
        d = post(self.url + "/v1/systemone", {"state": {"question": question}, "questions": {"q": {
            "type": "choice", "instructions": instructions, "criteria": crit}}}, 600)
        p = d["answers"]["q"]["probabilities"]
        return max(p, key=p.get)

    def run(self, text, portfolio, trace_path):
        t0 = time.time()
        stub = stub_pm.Stub(portfolio, trace_path)
        projects = {p["id"]: f"{p['goal']} (next: {p.get('next_step', '')})" for p in portfolio["projects"]}
        workers = "; ".join(f"{w['id']} on {w['project']}: {w['brief']}" for w in portfolio["workers"]) or "none"
        pj = self.ask(text, {**projects, "none": "no one project, or several, or a new one"},
                      f"Which project does this message concern? Running workers: {workers}.")
        acts = {"start": "start a new worker for the work asked",
                "message": "send an instruction to a running worker that already owns this work",
                "stop": "stop a running worker", "answer": "answer from what is already known, no worker",
                "ask": "ask the person which was meant, because it is ambiguous",
                "decision": "open a decision only the person may make (merge, settings, spend, a client, a failure)",
                "ack": "nothing: a status report that needs nobody"}
        ac = self.ask(text, acts, "What should the manager do with this message?")
        project = None if pj == "none" else pj
        worker = next((w["id"] for w in portfolio["workers"] if w["project"] == project), None)
        args = {"start": {"project": project, "runner": "local", "objective": "-", "output": "-", "boundaries": "-", "done_when": "-"},
                "message": {"worker": worker, "text": "-"}, "stop": {"worker": worker},
                "decision": {"kind": "question", "text": "-", "project": project}, "ask": {"question": "-"},
                "answer": {"text": "-"}}.get(ac)
        if ac != "ack":
            stub.call(ACTION_TOOLS[ac], {k: v for k, v in args.items() if v})
            stub.log({"note": "choice", "_project": project})
        return {"final_text": "", "launch_ts": t0, "wall_s": time.time() - t0, "tokens": tokens(turns=2),
                "offered_tools": [], "attempts": [], "error": None, "model": "d1", "choice": {"project": pj, "action": ac}}
