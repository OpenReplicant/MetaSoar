import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import run_day
from manager_env import _pm1a


class Fake(BaseHTTPRequestHandler):
    """A chat endpoint: first turn pm_portfolio, then a plain-text answer naming metasoar. Requests are kept in `seen`."""
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append(body)
        if sum(1 for m in body["messages"] if m["role"] == "tool") == 0:
            msg = {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "type": "function", "function": {
                "name": "pm_portfolio", "arguments": "{}"}}]}
        else:
            msg = {"role": "assistant", "content": "metasoar is on track"}
        out = json.dumps({"choices": [{"message": msg}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


DAY = {"id": "mini", "seed": 1, "storylines": [], "fillers": [
    {"at": 0, "scenario": {"id": "s01", "kind": "status", "message": "Where is the table-question experiment at?",
                           "expected": {"project": "metasoar", "action": "answer", "escalate": False}}},
    {"at": 60, "scenario": {"id": "s30", "kind": "escalate", "message": "Merge the manager PR.",
                            "expected": {"project": "substrate", "action": "decision", "escalate": True}}}]}


class RunDayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Fake)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def go(self, d, extra=()):
        days = os.path.join(d, "days")
        os.makedirs(days, exist_ok=True)
        with open(os.path.join(days, "mini.json"), "w") as f:
            json.dump(DAY, f)
        args = ["--arm", "fake", "--url", self.url, "--model", "m", "--days", "mini", "--days-dir", days,
                "--out-dir", os.path.join(d, "out"), *extra]
        with contextlib.redirect_stdout(io.StringIO()):
            return run_day.main(args)

    def test_writes_results_and_rollouts(self):
        with tempfile.TemporaryDirectory() as d:
            Fake.seen.clear()
            self.assertEqual(self.go(d), 0)
            with open(os.path.join(d, "out", "fake-base.days.json")) as f:
                res = json.load(f)
            day = res["days"][0]
            self.assertEqual(day["id"], "mini")
            self.assertEqual([a["tag"] for a in day["arrivals"]], ["filler.s01", "filler.s30"])
            self.assertTrue(day["arrivals"][0]["routing_ok"])   # a text answer naming metasoar
            self.assertFalse(day["arrivals"][1]["routing_ok"])  # an answer where a decision was labelled
            self.assertEqual(day["episode"]["routing"], 0.5)
            self.assertEqual(day["reward"], 0.5)
            self.assertEqual(day["episode"]["arrivals"], 2)
            self.assertEqual(day["arrivals"][0]["score"]["tokens"]["output"], 10)
            self.assertEqual([c["tool"] for c in day["arrivals"][0]["trace"]], ["pm_portfolio"])
            self.assertEqual(res["driver_info"]["model"], "m")
            # a fresh session per arrival: the second request chain starts again from system + this arrival's message only
            firsts = [b for b in Fake.seen if len(b["messages"]) == 2]
            self.assertEqual(len(firsts), 2)
            self.assertIn("Merge the manager PR.", firsts[1]["messages"][1]["content"])
            self.assertNotIn("table-question", json.dumps(firsts[1]["messages"]))
            lines = [json.loads(l) for l in open(os.path.join(d, "out", "fake-base.rollouts", "results.jsonl"))]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0]["reward"], 1.0)
            self.assertEqual(lines[0]["task"]["day"], "mini")
            self.assertEqual([m["role"] for m in lines[0]["messages"]], ["system", "user", "assistant", "tool", "assistant"])
            self.assertTrue(os.path.exists(os.path.join(d, "out", "fake-base.rollouts", "metadata.json")))

    def test_resume_and_env_options(self):
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, "c.json")
            json.dump({"candidates": [{"id": "c0", "env": {"inline_portfolio": True}}]}, open(c, "w"))
            Fake.seen.clear()
            self.assertEqual(self.go(d, ["--candidates", c, "--owner-first", "--speed", "2"]), 0)
            self.assertIn("Current portfolio", Fake.seen[0]["messages"][1]["content"])
            res = json.load(open(os.path.join(d, "out", "fake-c0.days.json")))
            self.assertTrue(res["owner_first"])
            self.assertEqual(res["speed"], 2.0)
            n = len(Fake.seen)
            self.go(d, ["--candidates", c, "--resume"])
            self.assertEqual(len(Fake.seen), n)  # the finished day was not re-run


if __name__ == "__main__":
    unittest.main()
