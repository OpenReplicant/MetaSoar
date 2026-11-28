import json
import os
import unittest

from manager_env import DayAction, DayEnvironment, ManagerAction, _pm1a
from manager_env import day as D
import replay
import stub_pm

HERE = os.path.dirname(os.path.abspath(__file__))


def call(name, **a):
    return ManagerAction(type="call_tool", tool_name=name, arguments=a)


BRIEF = dict(objective="x" * 20, output="x" * 20, boundaries="x" * 20, done_when="x" * 20)


def perfect(env, obs, skip_judge=False, queue_start_now=False):
    """The actions a manager that knows the label would take on this arrival (reads the environment's own label)."""
    d, a = env.day, env.arrival
    sc = d.scenario(a)
    exp, P, act = sc["expected"], sc["expected"]["project"], sc["expected"]["action"]
    out = []
    if act == "start":
        kind = exp.get("kind", "work")
        if kind == "judge" and skip_judge:
            return out
        out.append(call("pm_worker_start", project=P, runner=exp.get("runner", "local"), kind=kind, **BRIEF))
        pr = next(p for p in env.stub.p["projects"] if p["id"] == P)
        if a["tag"] == "queued.finished" and any(n.startswith("QUEUED") for n in pr.get("notes", [])):
            out.append(call("pm_worker_start", project=P, runner="local", kind="work", **BRIEF))  # the queued work
    elif act == "ask" and "queued" in exp.get("also", []):
        if queue_start_now:
            out.append(call("pm_worker_start", project=P, runner="local", kind="work", **BRIEF))
        else:
            out.append(call("pm_project_note", project=P, note="QUEUED: " + (sc.get("message") or "")))
            out.append(call("desktop_say", text=f"{P} has a writer running, so this is queued behind it."))
    elif act == "ask":
        out.append(call("desktop_ask", question="Which one do you mean?"))
    elif act == "answer":
        out.append(call("desktop_say", text=(f"Status of {P}: on track." if P else "Two workers running, nothing needs you.")))
    elif act == "decision":
        out.append(call("pm_decision_open", **({"project": P} if P else {}), kind="question", text="Needs your decision."))
    elif act == "message":
        out.append(call("pm_worker_message", worker=exp["worker"], text="Owner's answer: " + str(sc["event"]["answer"])))
    elif act == "stop":
        out.append(call("pm_worker_stop", worker=exp["worker"]))
        out.append(call("desktop_say", text="Stopped it."))  # a stop alone is not a reply to the owner
    return out


def play(env, policy=perfect, seconds=10.0, per_turn=None, **kw):
    obs = kw.pop("reset", None) or env.reset(**kw)
    n = 0
    while not obs.done:
        for act in policy(env, obs):
            obs = env.step(act)
        obs = env.step(DayAction(type="end_turn", seconds=per_turn(env) if per_turn else seconds))
        n += 1
        assert n < 400
    return obs


def train_day(i):
    return f"train-{i:02d}"


class DayGeneration(unittest.TestCase):
    def test_deterministic_by_seed_and_committed_files(self):
        for s in range(10):
            a, b = D.generate_day(s, f"train-{s:02d}"), D.generate_day(s, f"train-{s:02d}")
            self.assertEqual(a, b)
            on_disk = json.load(open(os.path.join(HERE, "days", f"train-{s:02d}.json")))
            self.assertEqual(a, on_disk)
            D.validate_day(on_disk)
        self.assertNotEqual(D.generate_day(0)["storylines"], D.generate_day(1)["storylines"])

    def test_day_size_and_fillers(self):
        for s in range(10):
            d = D.generate_day(s)
            static = sum(1 for _ in d["fillers"]) + sum({"burst": 4}.get(x["type"], 2 if x["type"] in
                         ("experiment", "plan_change", "queued", "limit") else 1) for x in d["storylines"])
            self.assertGreaterEqual(static, 15)
            self.assertLessEqual(static, 30)
            self.assertTrue(all(f["scenario"]["id"] in D.FILLERS for f in d["fillers"]))

    def test_filler_labels_do_not_name_initial_workers(self):
        _, pf = replay.load_world()
        scs, _ = replay.load_world()
        for sid in D.FILLERS:
            sc = next(s for s in scs if s["id"] == sid)
            self.assertNotIn("worker", sc["expected"], sid)
            self.assertNotIn(sc["expected"]["action"], ("message", "stop"), sid)


class DayRuns(unittest.TestCase):
    def test_perfect_manager_scores_one_on_every_train_day(self):
        env = DayEnvironment()
        types = set()
        for i in range(10):
            obs = play(env, day_id=train_day(i))
            ep = obs.episode
            self.assertEqual(ep["routing"], 1.0, (i, [(r["id"], r["score"]["tags"], r["score"]["named"]) for r in
                                                        env.day.records if not r["routing_ok"]]))
            self.assertEqual(obs.reward, 1.0)
            self.assertEqual(ep["dropped_loops"]["count"], 0, ep["dropped_loops"])
            self.assertEqual(ep["double_writers"]["count"], 0, ep["double_writers"])
            self.assertEqual(ep["interruptions"], 0)
            self.assertEqual(ep["cancelled_arrivals"], [])
            self.assertEqual(ep["owner_wait"]["unanswered"], 0)
            types |= {s["type"] for s in env.day.spec["storylines"]}
        self.assertEqual(types, set(D.STORY_TYPES))  # the ten days between them run all seven storylines

    def test_loops_are_opened_and_closed(self):
        env = DayEnvironment()
        play(env, day_id=train_day(0))
        names = {l["id"] for l in env.day.loops}
        self.assertIn("experiment-1:judge", names)
        self.assertIn("queued-w-22:queued_start", names)
        self.assertTrue(all(not l["open"] for l in env.day.loops))

    def test_never_judging_drops_the_experiment_loop(self):
        env = DayEnvironment()
        obs = play(env, day_id=train_day(0), policy=lambda e, o: perfect(e, o, skip_judge=True))
        dropped = {l["id"] for l in obs.episode["dropped_loops"]["loops"]}
        self.assertIn("experiment-1:judge", dropped)
        self.assertIn("queued-w-22:judge", dropped)
        self.assertLess(obs.episode["routing"], 1.0)

    def test_never_starting_the_experiment_drops_it_and_its_later_events_do_not_arrive(self):
        env = DayEnvironment()

        def nothing_on_request(e, o):
            return [] if e.arrival["tag"] == "experiment.request" else perfect(e, o)

        obs = play(env, day_id=train_day(0), policy=nothing_on_request)
        self.assertIn("experiment-1:judge", {l["id"] for l in obs.episode["dropped_loops"]["loops"]})
        self.assertFalse(any(r["tag"] == "experiment.finished" for r in env.day.records))

    def test_slow_manager_waits_longer_and_owner_first_lowers_it(self):
        waits = {}
        for label, seconds, of in (("fast", 5.0, False), ("slow", 400.0, False), ("slow_of", 400.0, True)):
            tot, p90s = [], []
            for i in range(10):
                env = DayEnvironment({"owner_first": of})
                ep = play(env, seconds=seconds, day_id=train_day(i)).episode
                tot += [r["wait_s"] for r in env.day.records if r["wait_s"] is not None]
                p90s.append(ep["owner_wait"]["p90_s"])
            waits[label] = (sum(tot) / len(tot), sum(p90s) / len(p90s))
        self.assertLess(waits["fast"][0], waits["slow"][0])
        self.assertLess(waits["slow_of"][0], waits["slow"][0])
        self.assertLess(waits["slow_of"][1], waits["slow"][1])

    def test_speed_scales_the_clock(self):
        a = play(DayEnvironment({"speed": 1.0}), day_id=train_day(2), seconds=300.0).episode
        b = play(DayEnvironment({"speed": 4.0}), day_id=train_day(2), seconds=300.0).episode
        self.assertGreater(b["owner_wait"]["median_s"], a["owner_wait"]["median_s"])

    def test_double_writers_counted(self):
        env = DayEnvironment()
        obs = play(env, day_id=train_day(0), policy=lambda e, o: perfect(e, o, queue_start_now=True))
        ep = obs.episode
        self.assertGreaterEqual(ep["double_writers"]["count"], 1)
        inc = ep["double_writers"]["incidents"][0]
        self.assertEqual(inc["project"], "substrate")
        self.assertIn("w-22", inc["with"])
        self.assertLess(ep["routing"], 1.0)  # the start is not a labelled answer for a busy project

    def test_kaggle_and_judge_starts_are_not_writers(self):
        env = DayEnvironment()
        env.reset(day={"id": "t", "seed": 1, "storylines": [], "fillers": [
            {"at": 0, "scenario": {"id": "s01", "kind": "status", "message": "x", "expected": {"project": "metasoar", "action": "answer", "escalate": False}}}]})
        env.step(call("pm_worker_start", project="metasoar", runner="kaggle", kind="work", **BRIEF))
        env.step(call("pm_worker_start", project="metasoar", runner="local", kind="judge", **BRIEF))
        self.assertEqual(env.day.double_writers, [])
        env.step(call("pm_worker_start", project="metasoar", runner="local", kind="work", **BRIEF))
        env.step(DayAction(type="end_turn", seconds=1))
        self.assertEqual(len(env.day.double_writers), 1)

    def test_deterministic_runs(self):
        a = play(DayEnvironment(), day_id=train_day(4))
        b = play(DayEnvironment(), day_id=train_day(4))
        self.assertEqual(a.episode, b.episode)
        env1, env2 = DayEnvironment(), DayEnvironment()
        play(env1, day_id=train_day(4)), play(env2, day_id=train_day(4))
        self.assertEqual([(r["id"], r["at"], r["delivered_at"]) for r in env1.day.records],
                         [(r["id"], r["at"], r["delivered_at"]) for r in env2.day.records])
        c = play(DayEnvironment(), seed=4)  # a generated day with the same seed is the committed one
        self.assertEqual(c.episode["arrivals"], a.episode["arrivals"])


class DayMechanics(unittest.TestCase):
    def test_portfolio_persists_and_sessions_are_fresh(self):
        env = DayEnvironment()
        obs = env.reset(day_id=train_day(1))
        self.assertTrue(obs.tools)
        env.step(call("pm_project_note", project="kernel", note="remember-me"))
        obs = env.step(DayAction(type="end_turn", seconds=1))
        self.assertFalse(obs.done)
        self.assertEqual(obs.step, 0)
        o = env.step(call("pm_portfolio", project="kernel"))
        self.assertIn("remember-me", o.tool_result)  # the portfolio is the manager's memory
        self.assertEqual(env.stub.trace[0]["tool"], "pm_portfolio")  # but the turn's trace starts empty

    def test_observation_and_rewards(self):
        env = DayEnvironment()
        obs = env.reset(day_id=train_day(1))
        self.assertTrue(obs.message)
        self.assertEqual(obs.arrival_index, 1)
        obs2 = env.step(DayAction(type="end_turn", seconds=30))
        self.assertIn(obs2.reward, (0.0, 1.0))
        self.assertIn("routing_ok", obs2.arrival_score)
        self.assertGreaterEqual(obs2.clock_s, 30)

    def test_idle_clock_jumps_to_next_arrival(self):
        env = DayEnvironment()
        spec = {"id": "t", "seed": 1, "storylines": [], "fillers": [
            {"at": 100, "scenario": {"id": "s01", "kind": "status", "message": "a", "expected": {"project": "metasoar", "action": "answer", "escalate": False}}},
            {"at": 5000, "scenario": {"id": "s05", "kind": "status", "message": "b", "expected": {"project": None, "action": "answer", "escalate": False}}}]}
        obs = env.reset(day=spec)
        self.assertEqual(obs.clock_s, 100)
        obs = env.step(DayAction(type="end_turn", seconds=10))
        self.assertEqual(obs.clock_s, 5000)
        obs = env.step(DayAction(type="end_turn", seconds=10))
        self.assertTrue(obs.done)
        self.assertEqual(obs.episode["arrivals"], 2)
        self.assertEqual(obs.episode["end_clock"], "10:23")
        with self.assertRaises(RuntimeError):
            env.step(DayAction(type="end_turn"))

    def test_owner_wait_uses_the_first_reply_call(self):
        env = DayEnvironment()
        spec = {"id": "t", "seed": 1, "storylines": [], "fillers": [
            {"at": 0, "scenario": {"id": "s01", "kind": "status", "message": "a", "expected": {"project": "metasoar", "action": "answer", "escalate": False}}}]}
        env.reset(day=spec)
        env.step(call("pm_portfolio"))
        env.step(ManagerAction(type="call_tool", tool_name="desktop_say", arguments={"text": "metasoar fine"}, metadata={"t": 7}))
        obs = env.step(DayAction(type="end_turn", seconds=60))
        self.assertEqual(obs.episode["owner_wait"]["median_s"], 7)

    def test_decision_answer_and_ambiguous_answer_arrive_after_their_delays(self):
        env = DayEnvironment()
        d = D.generate_day(1, "t")  # relay-w-21 and ambiguous
        play(env, day=d, seconds=10.0)
        recs = {r["tag"]: r for r in env.day.records}
        ask = next(r for r in env.day.records if r["tag"] == "ambiguous.request")
        ans = recs["ambiguous.answer"]
        self.assertEqual(ans["at"], ask["started_at"] + 10 + 300)  # the ask is made at the end of the turn: 5 min later
        rel = recs["decision_relay.needs_input"]
        self.assertEqual(recs["decision_relay.answered"]["at"], rel["started_at"] + 10 + 1200)

    def test_world_simulator_is_seeded_and_emits_events(self):
        env = DayEnvironment()
        env.reset(day={"id": "t", "seed": 7, "storylines": [], "fillers": [
            {"at": 0, "scenario": {"id": "s01", "kind": "status", "message": "a", "expected": {"project": "metasoar", "action": "answer", "escalate": False}}}]})
        env.step(call("pm_worker_start", project="kernel", runner="local", kind="work", **BRIEF))
        env.step(DayAction(type="end_turn", seconds=1))
        self.assertTrue(env.arrival["tag"].startswith("world."))  # the clock jumped to the worker's progress report
        self.assertGreater(env.day.clock, 1200)
        first = [(a["tag"], round(a["at"], 3)) for a in env.day.pending]
        tags = [env.arrival["tag"]]
        while not env.done:
            env.step(DayAction(type="end_turn", seconds=1))
            tags.append(env.arrival["tag"] if env.arrival else None)
        self.assertTrue(set(tags) - {None} <= {"world.progress", "world.finished", "world.limited", "world.failed"})
        env2 = DayEnvironment()
        env2.reset(day=env.day.spec)
        env2.step(call("pm_worker_start", project="kernel", runner="local", kind="work", **BRIEF))
        env2.step(DayAction(type="end_turn", seconds=1))
        self.assertEqual(first, [(a["tag"], round(a["at"], 3)) for a in env2.day.pending])  # same seed, same script

    def test_options_per_turn(self):
        env = DayEnvironment({"dedupe": True, "inline_portfolio": True})
        obs = env.reset(day_id=train_day(1))
        self.assertIn("Current portfolio", obs.message)
        env.step(call("kernel_search", query="table"))
        o = env.step(call("kernel_search", query="table"))
        self.assertIn("already made this exact call", o.tool_result)
        env.step(DayAction(type="end_turn", seconds=1))
        o = env.step(call("kernel_search", query="table"))  # a new turn: the dedupe memory is per turn
        self.assertNotIn("already made", o.tool_result)
        with self.assertRaises(ValueError):
            DayEnvironment({"nope": 1})

    def test_max_steps_ends_the_turn(self):
        env = DayEnvironment(max_steps=2)
        env.reset(day_id=train_day(1))
        env.step(call("pm_portfolio"))
        obs = env.step(call("pm_portfolio"))
        self.assertEqual(obs.arrival_index, 2)  # the turn ended and the next arrival is here
        self.assertIn("no final answer in 2 turns", obs.arrival_record["error"])


if __name__ == "__main__":
    unittest.main()
