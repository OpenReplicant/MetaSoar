import copy
import unittest

from manager_env import DayAction, DayEnvironment, ManagerAction, ManagerEnvironment, _pm1a, refs
import replay
import score as S


def world():
    return replay.load_world()[1]


def trace(*calls):
    return [{"seq": i, "ts": float(i), "tool": t, "arguments": a, "error": False, "result": "ok"} for i, (t, a) in enumerate(calls)]


def sc(project="substrate", action="answer", **kw):
    return {"id": "x", "kind": "status", "message": "status?", "expected": {"project": project, "action": action, "escalate": False, **kw}}


def scored(sc_, tr, final="", pf=None, hints=None):
    pf = pf or world()
    res = {"final_text": final, "launch_ts": 0.0, "wall_s": 1.0, "tokens": {"total_input": 0, "output": 0}, "offered_tools": [],
           "attempts": []}
    raw = S.score(sc_, pf, tr, res)
    return raw, refs.rescore(raw, sc_, pf, tr, final, hints)


class RefMapTests(unittest.TestCase):
    def setUp(self):
        self.pf = world()
        self.pf["workers"].append({"id": "w-31", "project": "morphogen", "state": "working", "brief": "x"})
        self.pf["decisions"].append({"id": "d-1", "project": "kernel", "kind": "question", "text": "merge?"})
        self.pf["decisions"].append({"id": "d-2", "kind": "notify", "text": "no project"})
        self.rm = refs.RefMap(self.pf, {"claude/w-31": "morphogen"})

    def test_worker(self):
        self.assertEqual(self.rm.find("w-31 is done; W-22 too"), {"w-31": "morphogen", "w-22": "substrate"})

    def test_pr_numbers(self):
        for t in ("PR 34", "PR #34", "#34", "pull request 34", "PR34", "PRs 33 and 34"):
            self.assertEqual(set(self.rm.find(t).values()), {"substrate"}, t)
        self.assertEqual(self.rm.find("PR 41"), {"PR 41": "morphogen"})
        self.assertEqual(self.rm.find("PR 999"), {})

    def test_branch(self):
        self.assertEqual(self.rm.find("pushed to claude/e19."), {"claude/e19": "metasoar"})
        self.assertEqual(self.rm.find("on claude/manager-agent"), {"claude/manager-agent": "substrate"})
        self.assertEqual(self.rm.find("claude/w-31"), {"claude/w-31": "morphogen", "w-31": "morphogen"})
        self.assertEqual(self.rm.find("claude/e19-other"), {})

    def test_decision(self):
        self.assertEqual(self.rm.find("see d-1"), {"d-1": "kernel"})
        self.assertEqual(self.rm.find("see d-2"), {})  # a decision with no project maps to none

    def test_experiment_and_knowledge_ids(self):
        self.assertEqual(self.rm.find("E-19 is running"), {"E-19": "metasoar"})
        self.assertEqual(self.rm.find("S-170 says"), {"S-170": "substrate"})
        self.assertEqual(self.rm.find("w-21 is not E-190"), {"w-21": "metasoar"})

    def test_ambiguous_experiment_id_is_not_mapped(self):
        pf = copy.deepcopy(self.pf)
        pf["projects"][1].setdefault("notes", []).append("same table as E-19")
        rm = refs.RefMap(pf)
        self.assertEqual(rm.find("E-19"), {})
        self.assertEqual(rm.find("E-18"), {"E-18": "metasoar"})

    def test_hints(self):
        rm = refs.RefMap(self.pf, {"w-40": "kernel", "claude/w-40": "kernel", "results/e19-dev.json": "metasoar"})
        self.assertEqual(set(rm.find("w-40 on claude/w-40, see results/e19-dev.json").values()), {"kernel", "metasoar"})


class RescoreTests(unittest.TestCase):
    def test_pr_only_reply_is_credited(self):
        tr = trace(("desktop_say", {"text": "PR 34 is still a draft; the design review is next."}))
        raw, new = scored(sc(), tr)
        self.assertFalse(raw["project_ok"])
        self.assertTrue(new["project_ok"])
        self.assertTrue(new["routing_ok"])
        self.assertIs(new["project_ok_raw"], False)
        self.assertEqual(new["named_refs"], ["substrate"])
        self.assertEqual(new["named"], ["substrate"])

    def test_closing_text_counts(self):
        raw, new = scored(sc(), [], final="Branch claude/manager-agent is waiting on review.")
        self.assertTrue(new["routing_ok"])

    def test_other_projects_worker_fails(self):
        tr = trace(("desktop_say", {"text": "w-21 is running the dev split."}))
        raw, new = scored(sc(), tr)
        self.assertFalse(new["project_ok"])
        self.assertFalse(new["routing_ok"])
        self.assertEqual(new["named_refs"], ["metasoar"])

    def test_two_projects_fail(self):
        tr = trace(("desktop_say", {"text": "PR 34 is a draft and PR 41 is open."}))
        self.assertFalse(scored(sc(), tr)[1]["routing_ok"])

    def test_nothing_named_still_fails(self):
        self.assertFalse(scored(sc(), trace(("desktop_say", {"text": "All fine."})))[1]["project_ok"])

    def test_decision_without_project_argument(self):
        tr = trace(("pm_decision_open", {"kind": "question", "text": "Merge PR 34 now?"}))
        raw, new = scored(sc(action="decision"), tr)
        self.assertFalse(raw["project_ok"])
        self.assertTrue(new["routing_ok"])

    def test_unscored_and_already_right_are_untouched(self):
        tr = trace(("desktop_say", {"text": "PR 34 is a draft."}))
        raw, new = scored(sc(project=None), tr)
        self.assertIsNone(new["project_ok"])
        tr = trace(("desktop_say", {"text": "substrate: PR 34 is a draft."}))
        raw, new = scored(sc(), tr)
        self.assertTrue(raw["project_ok"] and new["project_ok"])

    def test_reads_do_not_count(self):
        tr = trace(("kernel_search", {"query": "S-170"}), ("desktop_say", {"text": "Nothing to report."}))
        self.assertFalse(scored(sc(), tr)[1]["project_ok"])


class TierOptionTests(unittest.TestCase):
    def run_tier1(self, options):
        env = ManagerEnvironment(options)
        env.reset(scenario_id="s01")
        env.step(ManagerAction(type="call_tool", tool_name="desktop_say", arguments={"text": "PR 20 is a draft."}))
        return env.step(ManagerAction(type="end_turn", text=""))

    def test_tier1_is_raw_unless_project_refs(self):
        env = ManagerEnvironment({})
        env.reset(scenario_id="s01")
        sid = env.episode["scenario"]["expected"]["project"]
        self.assertEqual(sid, "metasoar")
        off = self.run_tier1({})
        self.assertNotIn("project_ok_raw", off.score)
        self.assertEqual(off.reward, 0.0)
        on = self.run_tier1({"project_refs": True})
        self.assertEqual(on.reward, 1.0)
        self.assertIs(on.score["project_ok_raw"], False)

    def test_day_tier_always_uses_refs(self):
        env = DayEnvironment()
        env.reset(day_id="train-00")
        obs = env.step(DayAction(type="end_turn", seconds=1.0))
        self.assertIn("project_ok_raw", obs.arrival_score)


if __name__ == "__main__":
    unittest.main()
