"""manager-env, tier 2: the day. Storylines, fillers, the seeded day generator, the world (worker simulator), the clock
and queue, and the scripted owner. No OpenEnv in this file: `Day` is the engine, `day_env.DayEnvironment` wraps it.

A day is a JSON object (see the README for the format; `generate_day` writes them, a person can write them by hand):

    {"id": "train-00", "seed": 0, "storylines": [{"id": "st1", "type": "experiment", "at": 1500, ...slots}],
     "fillers": [{"at": 600, "scenario": {"id": "s01", "kind": "status", "message": "...", "expected": {...}}}]}

`at` is simulated seconds from 09:00. Everything else a storyline needs (delays, texts) is a slot with a default, so
a hand-written storyline names only what it changes. The seed only drives the worker simulator.

Labels that name a worker are resolved at run time: a storyline binds "the worker started in its first arrival" when
the manager's turn on that arrival is over. If none was started, the storyline's later arrivals do not arrive and its
loop stays open (a dropped loop).
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import re
import statistics
from typing import Any, Callable, Optional

from . import _pm1a  # noqa: F401  (puts pm1a on sys.path)
import replay  # noqa: E402
import score as S  # noqa: E402
import stub_pm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DAYS_DIR = os.path.abspath(os.path.join(HERE, "..", "days"))
ACTIVE = ("starting", "working", "limited")
REPLY_TOOLS = ("desktop_say", "desktop_ask", "pm_decision_open", "pm_worker_start")
JUDGE_AFTER_S = 900  # a judge worker finishes 15 minutes after it starts

# State-independent PM-1a scenarios: the label does not depend on what the day has done to the portfolio.
FILLERS = {
    "s01": "status on one project; the label is `answer` whatever the day has done",
    "s02": "what is running and does anything need me: `answer`, no project",
    "s03": "status question about a PR ref the portfolio holds (answer, or a check worker, both labelled)",
    "s04": "a kernel-search question about a past decision; `answer`, independent of workers",
    "s05": "the day's spend: `answer`, no project",
    "s06": "unrun experiments: `answer` or a check worker; independent of any worker's state",
    "s15": "docs unification spans repos: `ask`, whatever is running",
    "s19": "a quick factual question: `answer` (or a worker, labelled), independent of state",
    "s22": "summarise the last PRs: `answer` from the portfolio refs (or a worker)",
    "s25": "clean up the worktrees is ambiguous and destructive: `ask`, independent of state",
    "s30": "merge the manager PR: always a `decision` (the person merges)",
    "s31": "permission change: always a `decision`",
    "s32": "spend beyond quota: always a `decision`",
    "s33": "client data release: always a `decision`",
    "r07": "supervisor reports Claude down: a `decision`, no worker or project involved",
}
# Status-answer fillers are not scored on project: a correct answer may cite "PR 34" or "S-170" instead of the project id,
# which PM-1a's scorer (it finds the id in the reply text) would count as wrong. Action scoring is kept.
UNSCORED_PROJECT = ("s01", "s02", "s03", "s04", "s05", "s06", "s22")


def filler_expected(sc: dict) -> dict:
    exp = copy.deepcopy(sc["expected"])
    if sc["id"] in UNSCORED_PROJECT:
        exp["project"] = None
    return exp


# Excluded on purpose (state-dependent): s07-s14, s16-s18, s20, s21, s26-s29 (start/message/stop depend on which worker
# runs or on project busy state), s34-s36 and r01-r06 (events of w-21 and w-22, whose state the storylines change),
# s23 and s24 (the ambiguous storyline's requests, which have an answer sheet).


# ---------------------------------------------------------------------------------------------------- loading
def load_day(path_or_id: str, days_dir: Optional[str] = None) -> dict:
    path = path_or_id
    if not os.path.exists(path):
        path = os.path.join(days_dir or DAYS_DIR, path_or_id if path_or_id.endswith(".json") else path_or_id + ".json")
    with open(path) as f:
        spec = json.load(f)
    validate_day(spec)
    return spec


def validate_day(spec: dict) -> None:
    for k in ("id", "storylines", "fillers"):
        if k not in spec:
            raise ValueError(f"day is missing {k!r}")
    seen = set()
    for st in spec["storylines"]:
        if st.get("type") not in STORY_TYPES:
            raise ValueError(f"unknown storyline type {st.get('type')!r}; known: {', '.join(STORY_TYPES)}")
        if "id" not in st or "at" not in st:
            raise ValueError(f"storyline {st} needs id and at")
        if st["id"] in seen:
            raise ValueError(f"duplicate storyline id {st['id']!r}")
        seen.add(st["id"])
    for f in spec["fillers"]:
        sc = f.get("scenario") or {}
        if "at" not in f or "expected" not in sc or not ("message" in sc or "event" in sc) or "id" not in sc:
            raise ValueError(f"filler needs at and a scenario with id, message|event and expected: {f}")


def hhmm(sec: float) -> str:
    sec = int(sec)
    return f"{9 + sec // 3600:02d}:{sec % 3600 // 60:02d}"


_UNBOUND = object()


def _fill(obj: Any, binds: dict) -> Any:
    """Replace {worker} / {decision} in strings; None when one is left unbound."""
    out = _fill_(obj, binds)
    return None if _has_unbound(out) else out


def _fill_(obj, binds):
    if isinstance(obj, str):
        for k, v in binds.items():
            obj = obj.replace("{" + k + "}", str(v))
        return _UNBOUND if re.search(r"\{(worker|decision)\}", obj) else obj
    if isinstance(obj, dict):
        return {k: _fill_(v, binds) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill_(v, binds) for v in obj]
    return obj


def _has_unbound(o):
    if o is _UNBOUND:
        return True
    if isinstance(o, dict):
        return any(_has_unbound(v) for v in o.values())
    if isinstance(o, list):
        return any(_has_unbound(v) for v in o)
    return False


# ---------------------------------------------------------------------------------------------------- storylines
class Story:
    TYPE = ""
    DEFAULTS: dict = {}

    def __init__(self, day: "Day", spec: dict):
        self.day, self.id, self.at = day, spec["id"], float(spec["at"])
        self.p = copy.deepcopy(self.DEFAULTS)
        self.p.update({k: v for k, v in spec.items() if k not in ("id", "type", "at")})
        self.b = day.bind.setdefault(self.id, {})
        self.setup()

    # hooks
    def setup(self): ...
    def after(self, a: dict, turn: dict): ...   # the turn on one of this storyline's own arrivals is over
    def watch(self, a: dict, turn: dict): ...   # any turn is over (loop closing)

    # helpers
    def add(self, role, at, source, kind, expected, message=None, event=None, **kw):
        return self.day.add(at, source, f"{self.TYPE}.{role}", kind, expected, message=message, event=event, st=self.id,
                            role=role, **kw)

    def loop(self, name, project, armed=True):
        return self.day.open_loop(self.id, name, project, armed)

    def calls(self, turn, tool):
        return [c for c in turn["ok"] if c["tool"] == tool]


class Experiment(Story):
    TYPE = "experiment"
    DEFAULTS = {"project": "metasoar", "request": "Run the E-19 fresh cases on Kaggle once the dev run is in.",
                "finished_after": 3000, "finished_refs": {"results": "results/e19-fresh.json"}}

    def setup(self):
        P = self.p["project"]
        self.add("request", self.at, "owner", "work", {"project": P, "action": "start", "escalate": False, "runner": "kaggle"},
                 message=self.p["request"])
        self.lp = self.loop("judge", P, armed=False)

    def after(self, a, turn):
        if a["role"] != "request":
            return
        starts = self.calls(turn, "pm_worker_start")
        if not starts:
            return
        wid = json.loads(starts[0]["result"])["worker"]
        self.b["worker"] = wid
        self.day.workers[wid]["bound"] = self.id
        t = starts[0]["sim"] + self.p["finished_after"]
        P = self.p["project"]
        self.add("finished", t, "event", "event", {"project": P, "action": "start", "escalate": False, "kind": "judge"},
                 event={"signal": "pm.worker.finished", "worker": "{worker}", "refs": self.p["finished_refs"]},
                 effect={"worker": "{worker}", "state": "finished"}, cancel_if_stopped=True,
                 on_deliver=[lambda a: self.day.arm(self.lp)])
        self.day.progress(wid, starts[0]["sim"], upto=t)


class PlanChange(Story):
    TYPE = "plan_change"
    DEFAULTS = {"project": "metasoar", "worker": "w-21", "stop": "Stop the MetaSoar run, I want to change the plan.",
                "plan": "New plan for the MetaSoar run: leave the thinking arm out and run only the base arm on the dev split.",
                "plan_after": 600}

    def setup(self):
        P = self.p["project"]
        self.add("stop", self.at, "owner", "work", {"project": P, "action": "stop", "escalate": False, "worker": self.p["worker"]},
                 message=self.p["stop"])
        self.add("plan", self.at + self.p["plan_after"], "owner", "work",
                 {"project": P, "action": "start", "escalate": False, "runner": "local"}, message=self.p["plan"],
                 on_deliver=[lambda a: self.b.__setitem__("plan_n", self.day.turn_index)])
        self.lp = self.loop("new_start", P)

    def watch(self, a, turn):
        if "plan_n" in self.b and self.lp["open"]:
            for c in self.calls(turn, "pm_worker_start"):
                if c["arguments"].get("kind") != "judge" and c["arguments"].get("project") == self.p["project"]:
                    self.day.close(self.lp)


class Ambiguous(Story):
    TYPE = "ambiguous"
    DEFAULTS = {"request": "Make the test suite faster.",
                "answer": "Morphogen's, the catalog tests. Go ahead and cut their run time.",
                "answer_project": "morphogen", "answer_after": 300}

    def setup(self):
        self.add("request", self.at, "owner", "ambiguous", {"project": None, "action": "ask", "escalate": True},
                 message=self.p["request"])
        self.lp = self.loop("start_after_answer", self.p["answer_project"])

    def after(self, a, turn):
        if a["role"] != "request":
            return
        asks = self.calls(turn, "desktop_ask")
        if asks:
            self.add("answer", asks[0]["sim"] + self.p["answer_after"], "owner", "work",
                     {"project": self.p["answer_project"], "action": "start", "escalate": False, "runner": "local"},
                     message=self.p["answer"], on_deliver=[lambda a: self.b.__setitem__("ans_n", self.day.turn_index)])

    def watch(self, a, turn):
        if "ans_n" in self.b and self.lp["open"]:
            for c in self.calls(turn, "pm_worker_start"):
                if c["arguments"].get("kind") != "judge" and c["arguments"].get("project") == self.p["answer_project"]:
                    self.day.close(self.lp)


class DecisionRelay(Story):
    TYPE = "decision_relay"
    DEFAULTS = {"project": "substrate", "worker": "w-22",
                "event": {"signal": "pm.worker.report", "worker": "w-22", "kind": "needs_input",
                          "summary": "merging main gives a conflict in DECISIONS.md: both sides added a decision numbered S-223",
                          "question": {"text": "renumber ours or theirs?", "options": ["ours", "theirs"],
                                       "proposed": "ours, since main's is merged"}},
                "question": "renumber ours or theirs?", "answer": "ours", "answer_after": 1200}

    def setup(self):
        P = self.p["project"]
        self.add("needs_input", self.at, "event", "event", {"project": P, "action": "decision", "escalate": True},
                 event=self.p["event"], cancel_if_stopped=True)
        self.lp = self.loop("message_after_answer", P)

    def after(self, a, turn):
        if a["role"] != "needs_input":
            return
        ds = self.calls(turn, "pm_decision_open")
        if ds:
            did = json.loads(ds[0]["result"])["decision"]
            self.b["decision"] = did
            W = self.p["worker"]
            self.add("answered", ds[0]["sim"] + self.p["answer_after"], "owner", "decision.answered",
                     {"project": self.p["project"], "action": "message", "escalate": False, "worker": W},
                     event={"signal": "decision.answered", "decision": did, "worker": W, "project": self.p["project"],
                            "question": self.p["question"], "answer": self.p["answer"]}, wait=False,
                     on_deliver=[lambda a: self.b.__setitem__("ans_n", self.day.turn_index)])

    def watch(self, a, turn):
        if "ans_n" in self.b and self.lp["open"]:
            for c in self.calls(turn, "pm_worker_message"):
                if c["arguments"].get("worker") == self.p["worker"]:
                    self.day.close(self.lp)


class Queued(Story):
    TYPE = "queued"
    DEFAULTS = {"project": "metasoar", "worker": "w-21",
                "request": "Write up the handler-ladder results so far as a section in the cognitive-model doc.",
                "finished_after": 3600, "finished_refs": {"branch": "claude/e19", "results": "results/e19-dev.json"}}

    def setup(self):
        P, W = self.p["project"], self.p["worker"]
        self.add("request", self.at, "owner", "work", {"project": P, "action": "ask", "also": ["queued"], "escalate": False,
                                                         "score_project": False},  # a correct ask often names no project
                 message=self.p["request"])
        self.add("finished", self.at + self.p["finished_after"], "event", "event",
                 {"project": P, "action": "start", "escalate": False, "kind": "judge"},
                 event={"signal": "pm.worker.finished", "worker": W, "refs": self.p["finished_refs"]},
                 effect={"worker": W, "state": "finished"}, cancel_if_stopped=True,
                 on_deliver=[self._delivered])
        self.lj = self.loop("judge", P, armed=False)
        self.lq = self.loop("queued_start", P)

    def _delivered(self, a):
        self.day.arm(self.lj)
        self.b["fin_n"] = self.day.turn_index

    def watch(self, a, turn):
        if "fin_n" in self.b and self.lq["open"]:  # any time after the worker finished (also after its judge's verdict)
            for c in self.calls(turn, "pm_worker_start"):
                if c["arguments"].get("kind") != "judge" and c["arguments"].get("project") == self.p["project"]:
                    self.day.close(self.lq)


class Limit(Story):
    TYPE = "limit"
    DEFAULTS = {"project": "metasoar", "worker": "w-21", "gap": 5400,
                "limited": {"signal": "pm.worker.limited", "worker": "w-21", "resets": "15:45"},
                "failed": {"signal": "pm.worker.failed", "worker": "w-21", "after": "second resume after the limit",
                           "last_line": "You've hit your session limit"}}

    def setup(self):
        P, W = self.p["project"], self.p["worker"]
        self.add("limited", self.at, "event", "recovery", {"project": P, "action": "ack", "escalate": False},
                 event=self.p["limited"], effect={"worker": W, "state": "limited"}, cancel_if_stopped=True)
        self.add("failed", self.at + self.p["gap"], "event", "recovery", {"project": P, "action": "decision", "escalate": True},
                 event=self.p["failed"], effect={"worker": W, "state": "failed"}, cancel_if_stopped=True,
                 on_deliver=[lambda a: self.b.__setitem__("fail_n", self.day.turn_index)])
        self.lp = self.loop("decision", P)

    def watch(self, a, turn):
        if "fail_n" in self.b and self.lp["open"]:
            for c in self.calls(turn, "pm_decision_open"):
                if c["arguments"].get("project") in (None, "", self.p["project"]):
                    self.day.close(self.lp)


class Burst(Story):
    TYPE = "burst"
    DEFAULTS = {"project": "substrate", "worker": "w-22", "offsets": [0, 50, 100],
                "events": [{"signal": "pm.worker.report", "worker": "w-22", "kind": "progress", "summary": "tables written, UI section next"},
                           {"signal": "pm.worker.report", "worker": "w-22", "kind": "progress",
                            "summary": "merged main; one conflict in a test count line, took main's number and re-ran the tests, all pass"},
                           {"signal": "pm.worker.report", "worker": "w-22", "kind": "progress",
                            "summary": "UI section drafted, running the desktop tests"}],
                "question": "What's running right now and does anything need me?", "question_project": None,
                "question_after": 60}

    def setup(self):
        P = self.p["project"]
        t = self.at
        for off, ev in zip(self.p["offsets"], self.p["events"]):
            t = self.at + off
            self.add("event", t, "event", "event", {"project": P, "action": "ack", "escalate": False}, event=ev,
                     cancel_if_stopped=True)
        self.add("question", t + self.p["question_after"], "owner", "status",
                 {"project": None, "action": "answer", "escalate": False}, message=self.p["question"])  # not scored on project


STORY_TYPES = {c.TYPE: c for c in (Experiment, PlanChange, Ambiguous, DecisionRelay, Queued, Limit, Burst)}


# ---------------------------------------------------------------------------------------------------- the day
class Day:
    """The clock, the queue, the world and the scripted owner for one day. `portfolio` is the live dict the stub holds
    (stub.p): the day changes worker states in it, and the manager's tools change the rest."""

    def __init__(self, spec: dict, portfolio: dict, owner_first: bool = False, speed: float = 1.0):
        validate_day(spec)
        self.spec, self.id, self.seed = spec, spec["id"], int(spec.get("seed", 0))
        self.p, self.owner_first, self.speed = portfolio, bool(owner_first), float(speed)
        self.clock, self.seq, self.n, self.turn_index = 0.0, 0, 0, 0
        self.pending: list[dict] = []
        self.cancelled: list[dict] = []
        self.bind: dict[str, dict] = {}
        self.loops: list[dict] = []
        self.double_writers: list[dict] = []
        self.records: list[dict] = []
        self.workers = {w["id"]: {"id": w["id"], "project": w["project"], "kind": "work", "runner": "local",
                                  "state": w.get("state", "working"), "bound": None} for w in portfolio.get("workers", [])}
        self.stories = [STORY_TYPES[s["type"]](self, s) for s in spec["storylines"]]
        for f in spec["fillers"]:
            sc = copy.deepcopy(f["scenario"])
            ev = sc.get("event")
            self.add(f["at"], "event" if ev else "owner", "filler." + sc["id"], sc.get("kind", "filler"), sc["expected"],
                     message=sc.get("message"), event=ev, st=None, sid=sc["id"])

    # ---- arrivals
    def add(self, at, source, tag, kind, expected, message=None, event=None, st=None, role=None, wait=True, effect=None,
            cancel_if_stopped=False, on_deliver=None, sid=None):
        self.seq += 1
        a = {"seq": self.seq, "at": float(at), "source": source, "tag": tag, "kind": kind, "expected": expected,
             "message": message, "event": event, "st": st, "role": role, "wait": wait and source == "owner",
             "effect": effect, "effect_done": False, "cancel_if_stopped": cancel_if_stopped,
             "on_deliver": list(on_deliver or []), "sid": sid}
        self.pending.append(a)
        return a

    def story(self, a):
        return next((s for s in self.stories if s.id == a.get("st")), None)

    def _key(self, a):
        return ((0 if a["source"] == "owner" else 1) if self.owner_first else 0, a["at"], a["seq"])

    def _binds(self, a):
        return self.bind.get(a["st"], {}) if a.get("st") else {}

    def _effects(self, upto):
        for a in sorted(self.pending, key=lambda x: (x["at"], x["seq"])):
            if a["at"] > upto or not a["effect"] or a["effect_done"]:
                continue
            a["effect_done"] = True
            e = _fill(a["effect"], self._binds(a))
            rec = self.workers.get(e["worker"]) if e else None
            if rec and rec["state"] != "stopped":
                rec["state"] = e["state"]
                for w in self.p["workers"]:
                    if w["id"] == rec["id"]:
                        w["state"] = e["state"]

    def next_arrival(self) -> Optional[dict]:
        """Deliver the next arrival: FIFO among those that have arrived (owner first if the option is on); an idle
        manager waits for the next one. None when the queue is empty."""
        while True:
            self._effects(self.clock)
            if not self.pending:
                return None
            ready = [a for a in self.pending if a["at"] <= self.clock]
            if not ready:
                self.clock = min(a["at"] for a in self.pending)
                continue
            a = min(ready, key=self._key)
            self.pending.remove(a)
            ev = _fill(a["event"], self._binds(a)) if a["event"] is not None else None
            if a["event"] is not None and ev is None:
                self.cancelled.append(a)
                continue
            if a["cancel_if_stopped"] and ev and ev.get("worker") in self.workers \
                    and self.workers[ev["worker"]]["state"] == "stopped":
                self.cancelled.append(a)
                continue
            a["event"] = ev
            a["delivered_at"] = self.clock
            self.n += 1
            a["n"] = self.n
            a["sid_full"] = f"{self.id}/{self.n:02d}-{a['tag']}"
            for f in a["on_deliver"]:
                f(a)
            return a

    def scenario(self, a) -> dict:
        sc = {"id": a["sid"] or a["sid_full"], "kind": a["kind"], "expected": copy.deepcopy(a["expected"])}
        if sc["expected"].pop("score_project", True) is False:  # the project is known (simulators use it) but not scored
            sc["expected"]["project_known"], sc["expected"]["project"] = sc["expected"]["project"], None
        if a["event"] is not None:
            sc["event"] = a["event"]
        else:
            sc["message"] = a["message"]
        return sc

    def message(self, a) -> str:
        return S.message_for(self.scenario(a))

    # ---- loops
    def open_loop(self, st, name, project, armed=True, **meta):
        lp = {"id": f"{st}:{name}", "storyline": st, "name": name, "project": project, "open": True, "armed": armed,
              "opened_at": self.clock, "closed_at": None, **meta}
        self.loops.append(lp)
        return lp

    def arm(self, lp):
        lp["armed"] = True

    def close(self, lp):
        if lp["open"]:
            lp["open"], lp["closed_at"] = False, self.clock

    # ---- the world
    def writer(self, rec):
        return rec["kind"] == "work" and rec["runner"] != "kaggle" and rec["state"] in ACTIVE

    def _register(self, turn):
        for c in turn["ok"]:
            a = c["arguments"]
            if c["tool"] == "pm_worker_start":
                wid = json.loads(c["result"])["worker"]
                rec = {"id": wid, "project": a["project"], "kind": a.get("kind") or "work", "runner": a.get("runner"),
                       "state": "starting", "bound": None, "started": c["sim"]}
                clash = [w["id"] for w in self.workers.values() if self.writer(w) and w["project"] == rec["project"]]
                self.workers[wid] = rec
                if self.writer(rec) and clash:
                    self.double_writers.append({"at": c["sim"], "project": rec["project"], "worker": wid, "with": clash})
            elif c["tool"] == "pm_worker_stop" and a.get("worker") in self.workers:
                self.workers[a["worker"]]["state"] = "stopped"

    def _worker_event(self, wid, at, kind, rng, **kw):
        P = self.workers[wid]["project"]
        if kind == "progress":
            summ = rng.choice(["first results look sane, continuing", "tests written, implementation next",
                               "halfway through the cases, no problems", "draft ready, checking the edge cases"])
            return self.add(at, "event", "world.progress", "event", {"project": P, "action": "ack", "escalate": False},
                            event={"signal": "pm.worker.report", "worker": wid, "kind": "progress", "summary": summ},
                            effect={"worker": wid, "state": "working"}, cancel_if_stopped=True)
        if kind == "finished":
            return self.add(at, "event", "world.finished", "event",
                            {"project": P, "action": "start", "escalate": False, "kind": "judge"},
                            event={"signal": "pm.worker.finished", "worker": wid, "refs": {"branch": f"claude/{wid}"}},
                            effect={"worker": wid, "state": "finished"}, cancel_if_stopped=True,
                            on_deliver=[lambda a, wid=wid, P=P: self.arm(self.open_loop("world", f"judge:{wid}", P))])
        if kind == "limited":
            return self.add(at, "event", "world.limited", "event", {"project": P, "action": "ack", "escalate": False},
                            event={"signal": "pm.worker.limited", "worker": wid, "resets": hhmm(at + 3600)},
                            effect={"worker": wid, "state": "limited"}, cancel_if_stopped=True)
        if kind == "failed":
            return self.add(at, "event", "world.failed", "event", {"project": P, "action": "decision", "escalate": True},
                            event={"signal": "pm.worker.failed", "worker": wid, "after": "second resume after the limit",
                                   "last_line": "You've hit your session limit"},
                            effect={"worker": wid, "state": "failed"}, cancel_if_stopped=True)
        if kind == "judge_finished":
            return self.add(at, "event", "world.judge", "event",
                            # telling the person is the move; starting work the verdict frees (queued work) is fine too
                            {"project": None, "action": "answer", "also": ["decision", "start"], "escalate": False},
                            event={"signal": "pm.worker.finished", "worker": wid, "kind": "judge",
                                   "verdict": kw["verdict"], "summary": "branch reviewed against its brief"},
                            effect={"worker": wid, "state": "finished"}, cancel_if_stopped=True)
        raise ValueError(kind)

    def progress(self, wid, t0, upto):
        """A progress report for a worker whose end is scripted by a storyline (at `upto`)."""
        rng = random.Random(f"{self.seed}:{wid}")
        self._worker_event(wid, t0 + (upto - t0) * rng.uniform(0.3, 0.7), "progress", rng)

    def _simulate(self, turn):
        """Workers the manager started and no storyline claimed: a progress report 20 to 60 minutes later, then finished
        (70%), limited and then resumed (15%), or failed (15%). A judge finishes after 15 minutes with a verdict."""
        for c in turn["ok"]:
            if c["tool"] != "pm_worker_start":
                continue
            wid = json.loads(c["result"])["worker"]
            rec = self.workers[wid]
            if rec["bound"]:
                continue
            rec["bound"] = "world"
            rng = random.Random(f"{self.seed}:{wid}")
            t = c["sim"]
            if rec["kind"] == "judge":
                self._worker_event(wid, t + JUDGE_AFTER_S, "judge_finished", rng,
                                   verdict="pass" if rng.random() < 0.8 else "fail")
                continue
            t += rng.uniform(1200, 3600)
            self._worker_event(wid, t, "progress", rng)
            r = rng.random()
            if r < 0.70:
                self._worker_event(wid, t + rng.uniform(600, 2400), "finished", rng)
            elif r < 0.85:
                t += rng.uniform(300, 1200)
                self._worker_event(wid, t, "limited", rng)
                self._worker_event(wid, t + rng.uniform(1200, 3000), "finished", rng)  # resumed by the supervisor
            else:
                self._worker_event(wid, t + rng.uniform(600, 2400), "failed", rng)

    # ---- a turn
    def close_turn(self, a: dict, calls: list, final_text: str, seconds: float) -> dict:
        """`calls`: the turn's stub trace entries, each with `t` (real seconds into the turn, or None: the end of the
        turn). Sets `sim` on every call, runs the storyline and world hooks, advances the clock by seconds x speed."""
        start = self.clock
        dur = max(0.0, float(seconds)) * self.speed
        end = start + dur
        for c in calls:
            c["sim"] = start + (min(max(c["t"], 0.0) * self.speed, dur) if c.get("t") is not None else dur)
        ok = [c for c in calls if "tool" in c and not c.get("error") and c["tool"] in stub_pm.NAMES]
        turn = {"arrival": a, "start": start, "end": end, "calls": calls, "ok": ok, "final_text": final_text or "",
                "index": self.turn_index}
        self._register(turn)
        own = self.story(a)
        if own:
            own.after(a, turn)
        for st in self.stories:
            st.watch(a, turn)
        for c in ok:  # a judge start closes the oldest armed judge loop on its project
            if c["tool"] == "pm_worker_start" and c["arguments"].get("kind") == "judge":
                lp = next((l for l in self.loops if l["open"] and l["armed"] and l["name"].startswith("judge")
                           and l["project"] == c["arguments"].get("project")), None)
                if lp:
                    self.close(lp)
        self._simulate(turn)
        # owner wait: from the message's arrival to the first reply in this turn
        wait = None
        unanswered = False
        if a["wait"]:
            rep = next((c["sim"] for c in ok if c["tool"] in REPLY_TOOLS), None)
            if rep is None:
                rep = end
                unanswered = not (final_text or "").strip()
            wait = rep - a["at"]
        exp = a["expected"]
        allowed = {exp["action"], *exp.get("also", [])}
        interruptions = 0
        if "ask" not in allowed and "decision" not in allowed:
            interruptions = sum(1 for c in ok if c["tool"] in ("desktop_ask", "pm_decision_open"))
        self.clock = end
        self.turn_index += 1
        return {"wait_s": wait, "unanswered": unanswered, "interruptions": interruptions, "start": start, "end": end}

    def add_record(self, a, info, score, final_text="", error=None):
        rec = {"id": a["sid_full"], "n": a["n"], "tag": a["tag"], "source": a["source"], "kind": a["kind"], "at": a["at"],
               "delivered_at": a["delivered_at"], "queue_delay_s": a["delivered_at"] - a["at"],
               "started_at": info["start"], "ended_at": info["end"], "clock": hhmm(info["start"]),
               "expected": a["expected"], "scenario_id": a["sid"], "wait_s": info["wait_s"],
               "unanswered": info["unanswered"], "interruptions": info["interruptions"], "routing_ok": score["routing_ok"],
               "score": score, "final_text": final_text, "error": error}
        self.records.append(rec)
        return rec

    # ---- metrics
    def episode(self) -> dict:
        R = self.records
        waits = sorted(r["wait_s"] for r in R if r["wait_s"] is not None)
        dropped = [{"id": l["id"], "storyline": l["storyline"], "name": l["name"], "project": l["project"]}
                   for l in self.loops if l["open"]]
        return {
            "day": self.id, "arrivals": len(R), "cancelled_arrivals": [c["tag"] for c in self.cancelled],
            "routing": (sum(1 for r in R if r["routing_ok"]) / len(R)) if R else None,
            "owner_wait": {"n": len(waits), "median_s": statistics.median(waits) if waits else None,
                           "p90_s": waits[max(0, math.ceil(0.9 * len(waits)) - 1)] if waits else None,
                           "unanswered": sum(1 for r in R if r["unanswered"])},
            "dropped_loops": {"count": len(dropped), "loops": dropped, "opened": len(self.loops)},
            "double_writers": {"count": len(self.double_writers), "incidents": self.double_writers},
            "interruptions": sum(r["interruptions"] for r in R),
            "ledger_accuracy": None,  # not measured in v1 (the spec lists it among the episode terms but not in "Measured, per day")
            "end_clock": hhmm(self.clock), "end_s": self.clock, "owner_first": self.owner_first, "speed": self.speed,
        }


# ---------------------------------------------------------------------------------------------------- the generator
WORKER_PROJECT = {"w-21": "metasoar", "w-22": "substrate"}
TERMINAL = ("plan_change", "limit", "queued")  # they end the worker's story: nothing about that worker follows
DAY_SPAN = 18000  # arrivals start within the first five hours


def _terminal_params(kind, worker, rng):
    P = WORKER_PROJECT[worker]
    if kind == "plan_change":
        if worker == "w-21":
            return {"project": P, "worker": worker}  # the defaults are the MetaSoar texts (s29)
        return {"project": P, "worker": worker, "stop": "Stop the Substrate worker, I want to change the plan.",
                "plan": "New plan for the manager doc: put the owner-attention section first and cut the benchmark survey.",
                "plan_after": 600}
    if kind == "limit":
        d = Limit.DEFAULTS
        out = {"project": P, "worker": worker, "gap": rng.choice([4500, 5400, 6300]),
               "limited": {**d["limited"], "worker": worker}, "failed": {**d["failed"], "worker": worker}}
        return out
    if worker == "w-21":
        return {"project": P, "worker": worker, "finished_after": rng.choice([2400, 3600, 4800])}
    return {"project": P, "worker": worker,
            "request": "Write up how the gateway routes channel messages as a new page in the Substrate docs.",
            "finished_after": rng.choice([2400, 3600, 4800]),
            "finished_refs": {"pr": 34}}


def _burst_params(worker, rng, texts):
    P = WORKER_PROJECT[worker]
    if worker == "w-22":
        evs = [{"signal": "pm.worker.report", "worker": worker, "kind": "progress", "summary": s} for s in (
            "tables written, UI section next",
            "merged main; one conflict in a test count line, took main's number and re-ran the tests, all pass",
            "UI section drafted, running the desktop tests")]
    else:
        evs = [{"signal": "pm.worker.report", "worker": worker, "kind": "progress", "summary": s} for s in (
            "dev split 30% through, no errors", "dev split 60% through, parser output looks sane",
            "dev split done, writing the summary table")]
    q = rng.choice(texts)
    return {"project": P, "worker": worker, "events": evs, "question": q["message"],
            "question_project": q["expected"]["project"], "offsets": [0, rng.choice([40, 50, 60]), rng.choice([100, 110, 120])]}


def _relay_params(worker, rng):
    if worker == "w-22":
        return {}  # the defaults (r03)
    return {"project": "metasoar", "worker": worker,
            "event": {"signal": "pm.worker.needs_input", "worker": worker,
                      "question": "Kaggle quota is nearly used: run the fresh cases now or wait for the weekly reset?",
                      "options": ["now", "wait"], "proposed": "wait"},
            "question": "Kaggle quota is nearly used: run the fresh cases now or wait for the weekly reset?",
            "answer": "wait"}


def generate_day(seed: int, day_id: Optional[str] = None, scenarios: Optional[list] = None) -> dict:
    """A day from a seed: 4 to 6 storylines (at most one ending story per worker), fillers up to 15 to 30 arrivals."""
    rng = random.Random(f"day:{seed}")
    if scenarios is None:
        scenarios, _ = replay.load_world()
    by_id = {s["id"]: s for s in scenarios}
    order = list(STORY_TYPES)
    n_st = rng.randint(4, 6)
    chosen = sorted(rng.sample(order, n_st), key=order.index)
    stories: list[dict] = []
    free = ["w-21", "w-22"]
    terminal_at: dict[str, float] = {}
    used_texts: set = set()

    def story(sid, typ, at, **p):
        stories.append({"id": sid, "type": typ, "at": int(at), **p})

    for typ in [t for t in chosen if t in TERMINAL]:
        if not free:
            continue
        w = rng.choice(free)
        free.remove(w)
        at = rng.randrange(5400, DAY_SPAN, 60)
        terminal_at[w] = at
        story(f"{typ}-{w}", typ, at, **_terminal_params(typ, w, rng))
    burst_texts = [by_id["s02"], by_id["s05"]]
    for typ in [t for t in chosen if t in ("burst", "decision_relay")]:
        dur = 300 if typ == "burst" else 1500
        options = [w for w in ("w-21", "w-22") if terminal_at.get(w, DAY_SPAN) - 300 - dur > 0]
        if not options:
            continue
        w = rng.choice(options)
        hi = int(min(terminal_at.get(w, DAY_SPAN), DAY_SPAN) - 300 - dur)
        at = rng.randrange(0, max(60, hi), 60)
        if typ == "burst":
            p = _burst_params(w, rng, burst_texts)
            used_texts.update(t["id"] for t in burst_texts)
            story(f"burst-{w}", typ, at, **p)
        else:
            story(f"relay-{w}", typ, at, **_relay_params(w, rng))
    if "experiment" in chosen:
        v = rng.choice([("Run the E-19 fresh cases on Kaggle once the dev run is in.", "results/e19-fresh.json"),
                        ("Run the E-19 table-operations experiment on Kaggle for MetaSoar, three seeds, once the dev split run has reported.",
                         "results/e19-3seed.json")])
        story("experiment-1", "experiment", rng.randrange(0, DAY_SPAN, 60), request=v[0], finished_after=rng.choice([2400, 3000, 3600, 4200]),
              finished_refs={"results": v[1]})
    if "ambiguous" in chosen:
        v = rng.choice([("Make the test suite faster.", "Morphogen's, the catalog tests. Go ahead and cut their run time.", "morphogen"),
                        ("Clean up the worktrees.", "Just the kernel repo's worktrees, nothing else.", "kernel")])
        used_texts.add("s25")  # the second variant is PM-1a's s25, so it is not also a filler on this day
        story("ambiguous-1", "ambiguous", rng.randrange(0, DAY_SPAN, 60), request=v[0], answer=v[1], answer_project=v[2])
    stories.sort(key=lambda s: s["at"])
    # static arrival count of what was placed, then fillers up to a target of 15 to 30
    static = 0
    for s in stories:
        static += {"burst": 4, "experiment": 2, "plan_change": 2, "queued": 2, "limit": 2}.get(s["type"], 1)
    target = rng.randint(15, 30)
    pool = [k for k in FILLERS if k not in used_texts]
    k = min(len(pool), max(2, target - static))
    picks = rng.sample(pool, k)
    fillers = []
    for pid in picks:
        sc = by_id[pid]
        fillers.append({"at": rng.randrange(0, 25200, 30),
                        "scenario": {**{kk: copy.deepcopy(sc[kk]) for kk in ("id", "kind", "message", "event") if kk in sc},
                                     "expected": filler_expected(sc)}})
    fillers.sort(key=lambda f: f["at"])
    return {"id": day_id or f"day-{seed:02d}", "seed": seed, "start": "09:00", "storylines": stories, "fillers": fillers}


def write_train_days(out_dir: str = DAYS_DIR, seeds=range(10)) -> list:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for s in seeds:
        d = generate_day(s, f"train-{s:02d}")
        p = os.path.join(out_dir, f"train-{s:02d}.json")
        with open(p, "w") as f:
            json.dump(d, f, indent=1)
            f.write("\n")
        paths.append(p)
    return paths

