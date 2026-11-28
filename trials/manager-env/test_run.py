import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import run
import parity
from manager_env import _pm1a
import replay
import gepa


class Fake(BaseHTTPRequestHandler):
    """A chat endpoint: first turn pm_portfolio, then desktop_say, then plain text. Requests are kept in `seen`."""
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append(body)
        tools_done = sum(1 for m in body["messages"] if m["role"] == "tool")
        if tools_done == 0:
            msg = {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "type": "function", "function": {
                "name": "pm_portfolio", "arguments": "{}"}}]}
        elif tools_done == 1:
            msg = {"role": "assistant", "content": "", "tool_calls": [{"id": "b", "type": "function", "function": {
                "name": "desktop_say", "arguments": json.dumps({"text": "E-19 in development on metasoar"})}}]}
        else:
            msg = {"role": "assistant", "content": "E-19 in development on metasoar"}
        out = json.dumps({"choices": [{"message": msg}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def scripted_handler(script):
    """A chat endpoint that answers turn n (counted by the tool messages so far) with script[n]: (tool, args) or text."""
    class H(Fake):
        seen = []

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            H.seen.append(body)
            step = script[min(sum(1 for m in body["messages"] if m["role"] == "tool"), len(script) - 1)]
            if isinstance(step, str):
                msg = {"role": "assistant", "content": step}
            else:
                msg = {"role": "assistant", "content": "", "tool_calls": [{"id": "c", "type": "function", "function": {
                    "name": step[0], "arguments": json.dumps(step[1])}}]}
            out = json.dumps({"choices": [{"message": msg}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
    return H


class RunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Fake)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def go(self, d, cands=None, extra=()):
        args = ["--arm", "fake", "--url", self.url, "--model", "m", "--only", "s01,s02", "--out-dir", d, *extra]
        if cands:
            args += ["--candidates", cands]
        with contextlib.redirect_stdout(io.StringIO()):
            return run.main(args)

    def test_run_writes_both_formats(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.go(d), 0)
            res = json.load(open(os.path.join(d, "fake-base.json")))
            self.assertEqual([r["id"] for r in res["runs"]], ["s01", "s02"])
            r = res["runs"][0]
            self.assertTrue(r["score"]["routing_ok"])
            self.assertEqual([c["tool"] for c in r["trace"]], ["pm_portfolio", "desktop_say"])
            self.assertEqual(r["final_text"], "E-19 in development on metasoar")
            self.assertEqual(r["score"]["tokens"]["output"], 15)
            self.assertEqual(res["driver_info"]["model"], "m")
            # replay.py report and gepa.py summary read it
            text = replay.report([os.path.join(d, "fake-base.json")])
            self.assertIn("Routing accuracy", text)
            self.assertEqual(gepa.load_results([os.path.join(d, "fake-base.json")])["fake-base"]["s01"], True)
            # harness records
            lines = [json.loads(l) for l in open(os.path.join(d, "fake-base.rollouts", "results.jsonl"))]
            self.assertEqual(len(lines), 2)
            e = lines[0]
            self.assertEqual(e["episode_id"], "fake-base-s01")
            self.assertEqual(e["reward"], 1.0)
            self.assertEqual([m["role"] for m in e["messages"]], ["system", "user", "assistant", "tool", "assistant", "tool", "assistant"])
            self.assertEqual([t["tool_name"] for t in e["tool_trace"]], ["pm_portfolio", "desktop_say"])
            self.assertTrue(os.path.exists(os.path.join(d, "fake-base.rollouts", "metadata.json")))

    def test_candidates_env_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, "c.json")
            json.dump({"candidates": [{"id": "c0", "env": {"inline_portfolio": True, "dedupe": True}},
                                      {"id": "c1", "prompt": None, "prefill": "off", "extra": {"k": 1}}]}, open(c, "w"))
            Fake.seen.clear()
            self.assertEqual(self.go(d, c), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "fake-c0.json")))
            self.assertTrue(os.path.exists(os.path.join(d, "fake-c1.json")))
            first = Fake.seen[0]["messages"][1]["content"]
            self.assertIn("Current portfolio", first)  # the environment applied inline_portfolio
            c1 = [b for b in Fake.seen if b.get("k") == 1]
            self.assertTrue(c1)  # extra reached the request
            self.assertNotIn("Current portfolio", c1[0]["messages"][1]["content"])
            r0 = json.load(open(os.path.join(d, "fake-c0.json")))["runs"][0]
            self.assertEqual(r0["env_intercepts"], {"dedupe": 0, "search_budget": 0})
            n = len(Fake.seen)
            self.go(d, c, ["--resume"])
            self.assertEqual(len(Fake.seen), n)  # nothing re-run

    def test_same_as_the_pm1a_driver(self):
        """The same model, env options and scenarios through drivers.OpenAICompatible.run and through the environment."""
        env_opts = {"inline_portfolio": True, "dedupe": True, "search_budget": 1}
        scs, pf = replay.load_world()
        drv = gepa.make_driver({"id": "x", "env": env_opts}, "fake", self.url, "m")
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, "c.json")
            json.dump({"candidates": [{"id": "x", "env": env_opts}]}, open(c, "w"))
            self.go(d, c)
            ours = {r["id"]: r for r in json.load(open(os.path.join(d, "fake-x.json")))["runs"]}
        for sc in scs[:2]:
            theirs = drv.run(replay.S.message_for(sc), replay.fresh(pf, sc), os.path.join(tempfile.gettempdir(), "mgr-trace.jsonl"))
            tr = replay.S.load_trace(os.path.join(tempfile.gettempdir(), "mgr-trace.jsonl"))
            os.remove(os.path.join(tempfile.gettempdir(), "mgr-trace.jsonl"))
            want = replay.S.score(sc, replay.fresh(pf, sc), tr, theirs)
            got = ours[sc["id"]]["score"]
            for k in ("tags", "named", "routing_ok", "action_ok", "project_ok", "tool_calls", "failed_calls"):
                self.assertEqual(got[k], want[k], k)
            self.assertEqual(ours[sc["id"]]["final_text"], theirs["final_text"])

    def test_router_options_same_as_the_pm1a_driver(self):
        """tools + noop_tool + stop_after_action: one fake endpoint through drivers.OpenAICompatible.run and the tier-1 env."""
        env_opts = {"tools": ["pm_portfolio", "desktop_say", "pm_worker_stop"], "noop_tool": True, "stop_after_action": True,
                    "inline_portfolio": True}
        scripts = {"stop": [("pm_portfolio", {}), ("pm_project_note", {"project": "metasoar", "note": "x"}),
                            ("desktop_say", {"text": "E-19 in development on metasoar"}), ("desktop_say", {"text": "again"})],
                   "noop": [("pm_portfolio", {}), ("pm_nothing", {}), ("desktop_say", {"text": "never"})]}
        scs, pf = replay.load_world()
        for name, script in scripts.items():
            H = scripted_handler(script)
            srv = HTTPServer(("127.0.0.1", 0), H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            url = f"http://127.0.0.1:{srv.server_port}"
            drv = gepa.make_driver({"id": "x", "env": env_opts}, "fake", url, "m")
            with tempfile.TemporaryDirectory() as d:
                c = os.path.join(d, "c.json")
                json.dump({"candidates": [{"id": "x", "env": env_opts}]}, open(c, "w"))
                args = ["--arm", "fake", "--url", url, "--model", "m", "--only", "s01,s02", "--out-dir", d, "--candidates", c]
                with contextlib.redirect_stdout(io.StringIO()):
                    run.main(args)
                ours = {r["id"]: r for r in json.load(open(os.path.join(d, "fake-x.json")))["runs"]}
                n_ours = len(H.seen)
                for sc in scs[:2]:
                    tp = os.path.join(d, "trace.jsonl")
                    theirs = drv.run(replay.S.message_for(sc), replay.fresh(pf, sc), tp)
                    tr = replay.S.load_trace(tp)
                    os.remove(tp)
                    want = replay.S.score(sc, replay.fresh(pf, sc), tr, theirs)
                    got = ours[sc["id"]]["score"]
                    for k in ("tags", "named", "routing_ok", "action_ok", "project_ok", "tool_calls", "failed_calls", "error"):
                        self.assertEqual(got[k], want[k], f"{name} {sc['id']} {k}")
                    self.assertEqual(ours[sc["id"]]["final_text"], theirs["final_text"])
                    self.assertEqual([c["tool"] for c in ours[sc["id"]]["trace"]], [c["tool"] for c in tr])
                # the same requests, tool list included (the first half of the log is the env's, the second the driver's)
                half = H.seen[:n_ours]
                self.assertEqual([b["tools"] for b in half], [b["tools"] for b in H.seen[n_ours:]])
                self.assertEqual([t["function"]["name"] for t in half[0]["tools"]],
                                 ["pm_portfolio", "pm_worker_stop", "desktop_say", "pm_nothing"])
            self.assertEqual(len(half), 2 * len(script[:3]) if name == "stop" else 2 * 2)

    def test_parity_on_committed_agent_traces(self):
        files = [f for f in parity.default_files() if "/agent/" in f]
        for f in files:
            rows, bad = parity.check(f)
            self.assertEqual(bad, [], f)
            self.assertEqual(len(rows), 43)


if __name__ == "__main__":
    unittest.main()
