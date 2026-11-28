"""Tests for the OpenAICompatible environment options and gepa.py, against a fake OpenAI-compatible server in a thread:
    cd trials/manager-eval/pm1a && python3 -I -m unittest discover -s . -p 'test_*.py'
"""
import hashlib
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import drivers  # noqa: E402
import gepa  # noqa: E402
import replay  # noqa: E402


def call(name, args, cid="c"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class Fake:
    """respond(body) -> an assistant message; every request body is kept in .requests."""

    def __init__(self, respond):
        self.respond, self.requests = respond, []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                data = json.dumps({"choices": [{"message": outer.respond(body)}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def scripted(msgs):
    """respond(): the next message of the list, in request order; plain text when it runs out."""
    it = iter(msgs)
    return lambda body: next(it, {"role": "assistant", "content": "done"})


def say_then_stop(body):
    if body["messages"][-1]["role"] == "tool":
        return {"role": "assistant", "content": "done"}
    return call("desktop_say", {"text": "hi"})


class Base(unittest.TestCase):
    def setUp(self):
        self.scenarios, self.portfolio = replay.load_world()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.trace = os.path.join(self.tmp.name, "trace.jsonl")
        self.servers = []

    def server(self, respond):
        f = Fake(respond)
        self.servers.append(f)
        self.addCleanup(f.close)
        return f

    def drive(self, respond, env=None, text="hello", **kw):
        f = self.server(respond)
        d = drivers.OpenAICompatible(f.url, "m", env=env, **kw)
        res = d.run(text, self.portfolio, self.trace)
        return f, res

    def traced(self):
        return [json.loads(l) for l in open(self.trace)] if os.path.exists(self.trace) else []


class EnvOptions(Base):
    def test_defaults_unchanged(self):
        f, res = self.drive(scripted([call("kernel_search", {"query": "x"}), call("kernel_search", {"query": "x"})]))
        self.assertEqual(f.requests[0]["messages"][1], {"role": "user", "content": "hello"})
        self.assertEqual(f.requests[0]["max_tokens"], 2048)
        self.assertNotIn("env_intercepts", res)
        self.assertEqual(len(self.traced()), 2)  # a repeat is sent to the stub
        self.assertEqual(res["tokens"]["turns"], 3)
        self.assertFalse(any(m.get("content") == drivers.OpenAICompatible.FINAL_NUDGE for m in f.requests[-1]["messages"]))

    def test_unknown_option_rejected(self):
        with self.assertRaises(ValueError):
            drivers.OpenAICompatible("http://x", env={"dedup": True})

    def test_inline_portfolio(self):
        f, res = self.drive(scripted([]), {"inline_portfolio": True})
        first = f.requests[0]["messages"][1]["content"]
        self.assertTrue(first.startswith("hello"))
        marker = "Current portfolio (what pm_portfolio returns):\n"
        self.assertIn(marker, first)
        import stub_pm
        expect = stub_pm.Stub(self.portfolio).call("pm_portfolio", {})[0]
        self.assertEqual(first.split(marker, 1)[1], expect)
        self.assertEqual(self.traced(), [])
        self.assertEqual(res["env_intercepts"], {"dedupe": 0, "search_budget": 0})

    def test_dedupe(self):
        f, res = self.drive(scripted([call("pm_portfolio", {"project": "metasoar", "x": 1}),
                                      call("pm_portfolio", {"x": 1, "project": "metasoar"}),
                                      call("pm_portfolio", {"project": "metasoar"})]), {"dedupe": True})
        tools = [m["content"] for r in f.requests[-1:] for m in r["messages"] if m["role"] == "tool"]
        self.assertEqual(tools[1], drivers.OpenAICompatible.DEDUPE_MSG)  # key order does not matter
        self.assertNotEqual(tools[2], drivers.OpenAICompatible.DEDUPE_MSG)  # different arguments
        self.assertEqual(len(self.traced()), 2)
        self.assertEqual(res["env_intercepts"]["dedupe"], 1)
        self.assertEqual(res["attempts"], ["pm_portfolio"] * 3)

    def test_search_budget(self):
        qs = [call("kernel_search", {"query": q}) for q in ("a", "b", "c")]
        f, res = self.drive(scripted(qs), {"search_budget": 1})
        tools = [m["content"] for m in f.requests[-1]["messages"] if m["role"] == "tool"]
        self.assertNotEqual(tools[0], drivers.OpenAICompatible.SEARCH_MSG)
        self.assertEqual(tools[1:], [drivers.OpenAICompatible.SEARCH_MSG] * 2)
        self.assertEqual(len(self.traced()), 1)
        self.assertEqual(res["env_intercepts"]["search_budget"], 2)

    def test_search_budget_zero_and_null(self):
        _, res = self.drive(scripted([call("kernel_search", {"query": "a"})]), {"search_budget": 0})
        self.assertEqual((res["env_intercepts"]["search_budget"], self.traced()), (1, []))
        os.remove(self.trace) if os.path.exists(self.trace) else None
        _, res = self.drive(scripted([call("kernel_search", {"query": "a"})] * 3), {"search_budget": None})
        self.assertEqual(res["env_intercepts"]["search_budget"], 0)
        self.assertEqual(len(self.traced()), 3)

    def test_final_nudge_and_max_turns(self):
        loop = lambda body: call("kernel_search", {"query": str(len(body["messages"]))})  # noqa: E731
        f, res = self.drive(loop, {"final_nudge": True, "max_turns": 3})
        self.assertEqual(len(f.requests), 3)
        nudge = drivers.OpenAICompatible.FINAL_NUDGE
        self.assertEqual(nudge, "Last turn: make your decision now with one tool call, or reply in plain text.")
        for r in f.requests[:2]:
            self.assertFalse(any(m.get("content") == nudge for m in r["messages"]))
        self.assertEqual(f.requests[2]["messages"][-1], {"role": "user", "content": nudge})
        self.assertEqual(res["error"], "no final answer in 3 turns")

    def test_max_turns_without_nudge(self):
        f, res = self.drive(lambda b: call("kernel_search", {"query": str(len(b["messages"]))}), {"max_turns": 2})
        self.assertEqual(len(f.requests), 2)
        self.assertFalse(any(m.get("content") == drivers.OpenAICompatible.FINAL_NUDGE for m in f.requests[1]["messages"]))

    def test_max_tokens(self):
        f, _ = self.drive(scripted([]), {"max_tokens": 77})
        self.assertEqual(f.requests[0]["max_tokens"], 77)

    def test_info(self):
        d = drivers.OpenAICompatible("http://x", env={"dedupe": True})
        raw = open(os.path.join(HERE, "manager.md"), "rb").read()
        self.assertEqual(d.info()["prompt_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(d.info()["env"], {"dedupe": True})


class RouterOptions(Base):
    def test_tools_subset_and_noop(self):
        f, res = self.drive(scripted([call("pm_portfolio", {}), call("pm_nothing", {}), call("desktop_say", {"text": "x"})]),
                            {"tools": ["pm_worker_start", "desktop_say"], "noop_tool": True})
        names = [t["function"]["name"] for t in f.requests[0]["tools"]]
        self.assertEqual(names, ["pm_worker_start", "desktop_say", "pm_nothing"])
        self.assertEqual(self.traced(), [])  # hidden tool not run, noop ends the turn before the say
        self.assertEqual(len(f.requests), 2)
        self.assertIsNone(res["error"])

    def test_stop_after_action(self):
        start = {"project": "kernel", "runner": "local", "objective": "o", "output": "o", "boundaries": "b", "done_when": "d"}
        f, res = self.drive(scripted([call("pm_portfolio", {}), call("pm_worker_start", start), call("pm_worker_start", start)]),
                            {"stop_after_action": True})
        self.assertEqual([c["tool"] for c in self.traced()], ["pm_portfolio", "pm_worker_start"])
        self.assertIsNone(res["error"])


def write(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f)


class Gepa(Base):
    def test_run_and_summary(self):
        f = self.server(say_then_stop)
        out = os.path.join(self.tmp.name, "out")
        ids = [s["id"] for s in self.scenarios[:2]]
        prompt = os.path.join(HERE, "_test_prompt.md")
        open(prompt, "w").write("You are a test manager.")
        self.addCleanup(os.remove, prompt)
        cands = os.path.join(self.tmp.name, "c.json")
        write(cands, {"candidates": [
            {"id": "c0", "prompt": None, "env": {}},
            {"id": "c1", "prompt": "_test_prompt.md", "env": {"dedupe": True, "max_tokens": 99}, "extra": {"seed": 3}, "prefill": "off"}]})
        lines = []
        a = SimpleNamespace(candidates=cands, arm="t", url=f.url, model="alias", only=",".join(ids), out_dir=out, resume=False)
        self.assertIsNone(gepa.run(a, log=lines.append))
        self.assertTrue(any("candidate c1" in l for l in lines))
        d0 = json.load(open(os.path.join(out, "t-c0.json"), encoding="utf-8"))
        d1 = json.load(open(os.path.join(out, "t-c1.json"), encoding="utf-8"))
        self.assertEqual([r["id"] for r in d0["runs"]], ids)
        self.assertEqual(d0["driver_info"]["env"], {})
        self.assertEqual(d1["driver_info"]["env"], {"dedupe": True, "max_tokens": 99})
        self.assertEqual(d1["driver_info"]["prompt_sha256"], hashlib.sha256(b"You are a test manager.").hexdigest())
        self.assertTrue(d1["driver_info"]["prompt"].endswith("_test_prompt.md"))
        self.assertEqual(d1["runs"][0]["env_intercepts"], {"dedupe": 0, "search_budget": 0})
        self.assertNotIn("env_intercepts", d0["runs"][0])
        sysmsgs = {r["messages"][0]["content"][:20] for r in f.requests}
        self.assertIn("You are a test manag", sysmsgs)
        self.assertEqual([r.get("seed") for r in f.requests if r["max_tokens"] == 99][:1], [3])

        # resume: nothing is asked again
        n = len(f.requests)
        a.resume = True
        gepa.run(a, log=lambda s: None)
        self.assertEqual(len(f.requests), n)

        base = os.path.join(self.tmp.name, "base.json")
        write(base, {"driver": "b", "runs": [{"id": ids[0], "score": {"routing_ok": True}}]})
        s = gepa.summarize(out, [base])
        self.assertEqual(s["scenarios"], ids)
        self.assertEqual(s["candidates"], ["t-c0", "t-c1"])
        self.assertEqual(s["baselines"], ["base"])
        self.assertEqual(s["matrix"]["base"], {ids[0]: True})
        self.assertEqual(s["accuracy"]["t-c0"]["ran"], 2)
        self.assertEqual(s["common_scenarios"], ids)
        self.assertEqual(s["pareto_front"], ["t-c0", "t-c1"])  # identical vectors: neither dominates
        with open(os.devnull, "w") as dn:
            old, sys.stdout = sys.stdout, dn
            try:
                gepa.main(["summary", out, "--baseline", base])
            finally:
                sys.stdout = old
        self.assertTrue(os.path.exists(os.path.join(out, "summary.json")))
        self.assertIn("Pareto front", gepa.markdown(s))
        # summary.json in the dir is not read as a candidate on the next summary
        self.assertEqual(gepa.summarize(out)["candidates"], ["t-c0", "t-c1"])

    def test_pareto(self):
        d = os.path.join(self.tmp.name, "p")
        os.makedirs(d)
        mk = lambda ok: {"runs": [{"id": f"s{i}", "score": {"routing_ok": v}} for i, v in enumerate(ok)]}  # noqa: E731
        write(os.path.join(d, "a-x.json"), mk([1, 1, 0]))
        write(os.path.join(d, "a-y.json"), mk([1, 0, 1]))
        write(os.path.join(d, "a-z.json"), mk([1, 0, 0]))  # dominated by both
        write(os.path.join(d, "a-w.json"), mk([1, 1]))  # ran fewer: common set is s0,s1
        s = gepa.summarize(d, scenario_order=["s0", "s1", "s2"])
        self.assertEqual(s["common_scenarios"], ["s0", "s1"])
        self.assertEqual(s["pareto_front"], ["a-w", "a-x"])
        self.assertEqual(s["accuracy"]["a-w"]["ran"], 2)


class ReplayDefaults(Base):
    def test_run_all_without_env_matches_old_behaviour(self):
        f = self.server(say_then_stop)
        out = os.path.join(self.tmp.name, "o.json")
        d = drivers.OpenAICompatible(f.url, "m")
        runs, _ = replay.run_all(d, self.scenarios[:1], self.portfolio, out, log=lambda s: None)
        self.assertNotIn("env_intercepts", runs[0])
        self.assertEqual(f.requests[0]["messages"][1]["content"], replay.S.message_for(self.scenarios[0]))

    def test_env_flag_parsed(self):
        a = SimpleNamespace(driver="openai-compatible", url="http://x", model="m", prompt=None, extra=None, label="l",
                            prefill="off", env='{"dedupe": true}', effort="low")
        self.assertEqual(replay.make_driver(a).env, {"dedupe": True})


if __name__ == "__main__":
    unittest.main()
