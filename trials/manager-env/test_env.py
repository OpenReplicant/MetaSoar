import json
import unittest

from manager_env import ManagerAction, ManagerEnvironment, _pm1a
import stub_pm
import score as S


def call(name, **a):
    return ManagerAction(type="call_tool", tool_name=name, arguments=a)


class EnvTest(unittest.TestCase):
    def test_reset_by_id_and_seed(self):
        env = ManagerEnvironment()
        o = env.reset(scenario_id="s01")
        self.assertEqual(o.scenario_id, "s01")
        self.assertEqual(o.message, S.message_for(env.by_id["s01"]))
        self.assertEqual(o.tools, stub_pm.TOOLS)
        self.assertFalse(o.done)
        self.assertEqual(env.reset(seed=2).scenario_id, env.scenarios[2]["id"])
        self.assertEqual(env.reset(seed=2 + len(env.scenarios)).scenario_id, env.scenarios[2]["id"])
        with self.assertRaises(ValueError):
            env.reset(scenario_id="nope")

    def test_event_message(self):
        env = ManagerEnvironment()
        o = env.reset(scenario_id="s35")
        self.assertTrue(o.message.startswith('<channel signal="pm.worker.report">'))

    def test_end_turn_scores_with_score_unchanged(self):
        env = ManagerEnvironment()
        env.reset(scenario_id="s01")  # status on metasoar: answer
        o = env.step(call("pm_portfolio", project="metasoar"))
        self.assertFalse(o.done)
        self.assertIn("metasoar", o.tool_result)
        o = env.step(ManagerAction(type="end_turn", text="E-19 is in development on metasoar."))
        self.assertTrue(o.done)
        ep = env.episode
        direct = S.score(ep["scenario"], ep["portfolio"], ep["trace"], ep["res"])
        self.assertEqual(o.metadata["score"], direct)
        self.assertEqual(o.reward, 1.0 if direct["routing_ok"] else 0.0)
        self.assertEqual(o.reward, 1.0)

    def test_wrong_routing_is_zero(self):
        env = ManagerEnvironment()
        env.reset(scenario_id="s01")
        o = env.step(call("pm_worker_start", project="metasoar", runner="local", objective="x" * 20, output="x" * 20,
                          boundaries="x" * 20, done_when="x" * 20))
        o = env.step(ManagerAction(type="end_turn", text=""))
        self.assertEqual(o.reward, 0.0)
        self.assertFalse(o.metadata["score"]["routing_ok"])

    def test_fresh_portfolio_each_episode(self):
        env = ManagerEnvironment()
        env.reset(scenario_id="s01")
        env.step(call("pm_project_note", project="metasoar", note="mark"))
        env.reset(scenario_id="s01")
        o = env.step(call("pm_portfolio", project="metasoar"))
        self.assertNotIn("mark", o.tool_result)

    def test_errors_and_unknown_tools(self):
        env = ManagerEnvironment()
        env.reset(scenario_id="s01")
        o = env.step(call("pm_worker_stop", worker="w-nope"))
        self.assertTrue(o.tool_error)
        o = env.step(call("rm_rf", x=1))
        self.assertTrue(o.tool_error)
        o = env.step(ManagerAction(type="end_turn", text="done"))
        self.assertIn("rm_rf", env.episode["res"]["attempts"])
        self.assertEqual(o.metadata["score"]["failed_calls"], 1)  # the stub's failed call; the unknown tool is an attempt

    def test_max_steps(self):
        env = ManagerEnvironment(max_steps=3)
        env.reset(scenario_id="s01")
        for _ in range(2):
            self.assertFalse(env.step(call("pm_portfolio")).done)
        o = env.step(call("pm_portfolio"))
        self.assertTrue(o.done)
        self.assertIn("no final answer in 3 turns", o.metadata["error"])
        with self.assertRaises(RuntimeError):
            env.step(call("pm_portfolio"))

    def test_default_max_steps_is_10(self):
        self.assertEqual(ManagerEnvironment().max_steps, 10)

    def test_inline_portfolio(self):
        env = ManagerEnvironment({"inline_portfolio": True})
        o = env.reset(scenario_id="s01")
        self.assertIn("Current portfolio (what pm_portfolio returns):\n{", o.message)
        self.assertNotIn("Current portfolio", ManagerEnvironment().reset(scenario_id="s01").message)
        self.assertEqual(env.episode["trace"], [])  # not a traced call

    def test_dedupe(self):
        env = ManagerEnvironment({"dedupe": True})
        env.reset(scenario_id="s01")
        a = env.step(call("kernel_search", query="table"))
        b = env.step(call("kernel_search", query="table"))
        self.assertNotEqual(a.tool_result, b.tool_result)
        self.assertIn("already made this exact call", b.tool_result)
        self.assertEqual(len(env.episode["trace"]), 1)
        o = env.step(ManagerAction(type="end_turn", text="x"))
        self.assertEqual(o.metadata["env_intercepts"], {"dedupe": 1, "search_budget": 0})

    def test_search_budget(self):
        env = ManagerEnvironment({"search_budget": 1})
        env.reset(scenario_id="s01")
        env.step(call("kernel_search", query="a"))
        o = env.step(call("kernel_search", query="b"))
        self.assertIn("Search budget spent", o.tool_result)
        self.assertEqual(len(env.episode["trace"]), 1)

    def test_final_nudge(self):
        env = ManagerEnvironment({"final_nudge": True, "max_turns": 3})
        self.assertEqual(env.max_steps, 3)
        self.assertIsNone(env.reset(scenario_id="s01").nudge)
        self.assertIsNone(env.step(call("pm_portfolio")).nudge)
        o = env.step(call("kernel_search", query="x"))
        self.assertIn("Last turn", o.nudge)

    def test_unknown_option(self):
        with self.assertRaises(ValueError):
            ManagerEnvironment({"bogus": 1})

    def test_mcp_actions_accepted(self):
        from openenv.core.env_server.mcp_types import CallToolAction, ListToolsAction
        env = ManagerEnvironment()
        env.reset(scenario_id="s01")
        self.assertEqual(env.step(ListToolsAction()).tools, stub_pm.TOOLS)
        o = env.step(CallToolAction(tool_name="pm_portfolio", arguments={}))
        self.assertEqual(o.step, 1)

    def test_http_app(self):
        from fastapi.testclient import TestClient
        from server.app import app
        c = TestClient(app)
        r = c.post("/reset", json={"scenario_id": "s01"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["observation"]["scenario_id"], "s01")
        with c.websocket_connect("/ws") as ws:
            ws.send_json({"type": "reset", "data": {"scenario_id": "s01"}})
            self.assertEqual(ws.receive_json()["data"]["observation"]["scenario_id"], "s01")
            ws.send_json({"type": "step", "data": {"type": "call_tool", "tool_name": "pm_portfolio", "arguments": {}}})
            self.assertEqual(ws.receive_json()["data"]["observation"]["step"], 1)
            ws.send_json({"type": "step", "data": {"type": "end_turn", "text": "E-19 on metasoar"}})
            d = ws.receive_json()["data"]
            self.assertTrue(d["done"])
            self.assertEqual(d["reward"], 1.0)
            self.assertIn("routing_ok", d["observation"]["score"])


if __name__ == "__main__":
    unittest.main()
