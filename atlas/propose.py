"""The atlas's model tier (docs/atlas.md, "The first experiment"): when play stops explaining itself, a model
proposes a claim about what the level asks, as a hypothesis in one sentence and a small program that the agent
then tests by playing.

The trigger is a surprise of the plainest kind: a level that has gone `PATIENCE` steps without completing. The
model sees what the agent sees and has learned, nothing of the game's source: the frame as hex, the objects, the
claims so far (what touching each kind did, the budget, the refills), and a log of notable events with the cells
that changed. It answers with `plan(w)`, a function the agent calls each step, which names the kind of object to
touch next (or None, and the agent goes on exploring). A plan that brings no level in `TRIAL` steps is refuted;
the next call is told what it proposed and what happened.

Every call is cached by the hash of its prompt, so an experiment can be replayed without calling again. With no
way to call a model from where the episode runs (the sandbox has no network), the cache is the mailbox: a prompt
not yet answered is written to `<cache>/pending/<key>.txt` and the episode stops (`Pending`); whoever answers
writes `<cache>/<key>.json` ({"model": ..., "text": ...}), and the episode, replayed from the start with the same
seed, reaches the same prompt and reads the answer.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PATIENCE = 40  # steps on a level without completing it before asking
TRIAL = 60  # steps a plan has to bring a level before it counts as refuted
CALLS_PER_LEVEL = 4
MODEL = "claude-haiku-5-5"  # the label recorded with each answer; whoever answers the mailbox sets it
HEX = "0123456789abcdef"

SAFE = {n: __builtins__[n] if isinstance(__builtins__, dict) else getattr(__builtins__, n) for n in (
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int", "isinstance", "len", "list", "map",
    "max", "min", "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip", "frozenset",
    "ValueError", "KeyError", "IndexError", "Exception")}

GUIDE = """You are the hypothesis-forming part of an agent that is learning an unknown grid game by playing it.
The agent cannot read the game's rules or code. It sees a 64x64 frame of colours 0-15 (written below as hex digits,
one row per line, row 0 first), and it has learned some things by experiment, listed below.

The agent may control a player that it moves with plain actions and that interacts with objects by moving into
contact with them ("touching"); it routes to any object you name, through what it believes passable, picking up a
refill on the way if its step budget would run out. Some games also or instead take clicks on a point, and some have
actions with no direction (their effect is in the events below). Your job is to say what this level most likely requires, given the
evidence, and write a small program that steers the agent's touching toward it.

Write:
1. one line starting "HYPOTHESIS:" with the claim in plain words;
2. one ```python block defining `plan(w)`, called once per step, returning what to do next, or a list of options
   in order of preference (the first that can be done now is done), or None to let the agent explore on its own.
   An option is a kind, a (colour, size) tuple, to walk into; ("click", kind) to click an object of that kind; or an
   action's name, such as "ACTION5", to do it.

`w` has:
- w.step: steps since this level began; w.frame: list of 64 strings of hex digits (the current frame)
- w.region(x0, y0, x1, y1): the frame's rows y0..y1, columns x0..x1 inclusive, as a list of hex strings
- w.objects: list of dicts with kind (colour, size), color, size, x, y, w, h (bounding box), cx, cy (a cell on it)
- w.player: the player's object dict, or None
- w.touched: dict kind -> dict outcome -> count, for outcomes take, event, harm, level, block, none
  (event: the scene changed beyond what was touched; block: the touch was refused; take: it vanished)
- w.events: the notable events of this level, oldest first (dicts: step, action, outcome, kinds, changed: list of
  boxes (x0, y0, x1, y1) of changed cells, before, after: those regions as hex rows, when small)
- w.budget, w.left: the step budget the agent has learned (or None) and how many steps are left of it
- w.refills: kinds that refill the budget when taken
- w.presses: how many times this life a touch changed the scene beyond what was touched
- w.memory: a dict that persists between calls, for your own state
Only builtins like len, range, min, max, sorted, set, dict, list, tuple, zip, enumerate, any, all, sum, abs are
available; no imports. Keep it short. If the plan raises an exception the agent ignores it for that step.
"""


def hexrows(g, x0=0, y0=0, x1=None, y1=None):
    x1 = g.shape[1] - 1 if x1 is None else x1
    y1 = g.shape[0] - 1 if y1 is None else y1
    return ["".join(HEX[int(c)] for c in row[x0:x1 + 1]) for row in g[y0:y1 + 1]]


class World:
    """What a plan sees: built from the agent each step."""

    def __init__(self, agent, g, objs, mk, me):
        self.step = agent.level_steps
        self._g = g
        self.frame = hexrows(g)
        self.objects = [{"kind": (o["color"], o["size"]), "color": o["color"], "size": o["size"], "x": o["x"],
                         "y": o["y"], "w": o["w"], "h": o["h"], "cx": o["cx"], "cy": o["cy"]} for o in objs]
        self.player = None if me is None else {"kind": (me["color"], me["size"]), **{k: me[k] for k in
                                                ("color", "size", "x", "y", "w", "h", "cx", "cy")}}
        self.touched = {k: dict(v) for k, v in agent.contact.items()}
        self.events = agent.events
        self.budget = agent.budget
        self.left = None if agent.budget is None else agent.budget - agent.since
        self.refills = [k for k, n in agent.refill.items() if n]
        self.presses = agent.presses
        self.memory = agent.plan_memory

    def region(self, x0, y0, x1, y1):
        return hexrows(self._g, max(0, x0), max(0, y0), min(63, x1), min(63, y1))


class Pending(Exception):
    """A prompt with no answer yet in the cache (offline mode)."""

    def __init__(self, key):
        super().__init__(key)
        self.key = key


class Proposer:
    def __init__(self, cache_dir=None, ask=None, model=MODEL):
        """`ask(prompt) -> (text, usage)` answers in process; without it, unanswered prompts go to the mailbox."""
        self.cache = Path(cache_dir) if cache_dir else None
        self.ask = ask
        self.model = model
        self.calls = []  # (level, hypothesis, cached, usage)

    def propose(self, prompt, level):
        key = hashlib.sha256(prompt.encode()).hexdigest()[:20]
        path = self.cache / f"{key}.json" if self.cache else None
        if path and path.exists():
            d = json.loads(path.read_text())
            cached = True
        elif self.ask is None:
            (self.cache / "pending").mkdir(parents=True, exist_ok=True)
            (self.cache / "pending" / f"{key}.txt").write_text(prompt)
            raise Pending(key)
        else:
            text, usage = self.ask(prompt)
            d = {"model": self.model, "text": text, "usage": usage}
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(d))
            cached = False
        hyp = next((ln.split(":", 1)[1].strip() for ln in d["text"].splitlines() if ln.startswith("HYPOTHESIS:")), "")
        self.calls.append({"level": level, "hypothesis": hyp, "cached": cached, "usage": d.get("usage")})
        return hyp, compile_plan(d["text"])


def compile_plan(text):
    m = re.search(r"```python\s*\n(.*?)```", text, re.S)
    if not m:
        return None
    env = {"__builtins__": SAFE}
    try:
        exec(compile(m.group(1), "<plan>", "exec"), env)
    except Exception:
        return None
    f = env.get("plan")
    return f if callable(f) else None


def prompt_for(agent, g, objs, me, tried):
    lines = [GUIDE, "## What the agent has learned"]
    mk = agent.mover()
    lines.append(f"- actions: {agent.names}; those taking a point: {sorted(agent.point)}")
    if mk is None:
        lines.append("- no player found yet (nothing the plain actions move)")
    else:
        lines.append(f"- the player: kind {mk}, at {None if me is None else (me['x'], me['y'], me['w'], me['h'])}; "
                     f"moves: " + ", ".join(f"{a} {agent.vec(a, mk)}" for a in agent.plain))
    clicks = "; ".join(f"{k}: {dict(v)}" for k, v in agent.clicked.items() if v)
    if clicks:
        lines.append("- what clicking each kind did: " + clicks)
    lines.append(f"- step budget: {agent.budget} (steps since it last filled: {agent.since}); refills: "
                 f"{[k for k, n in agent.refill.items() if n]}")
    lines.append("- passable colours (passed, blocked): " + json.dumps({str(c): v for c, v in agent.passable.items()}))
    lines.append("- what touching each kind did: " + "; ".join(f"{k}: {dict(v)}" for k, v in agent.contact.items() if v))
    lines.append(f"- steps on this level: {agent.level_steps}; levels completed: {agent.prev['levels']}")
    lines.append("\n## Objects now (kind, box x y w h)")
    lines += [f"- {(o['color'], o['size'])} at {o['x']} {o['y']} {o['w']} {o['h']}" for o in objs[:40]]
    lines.append("\n## Notable events this level (newest last)")
    for e in agent.events[-25:]:
        s = f"- step {e['step']}: {e['action']} -> {e['outcome']}, touched {e['kinds']}, changed {e['changed']}"
        if e.get("before"):
            s += f"\n  before {e['before']}\n  after  {e['after']}"
        lines.append(s)
    if tried:
        lines.append("\n## Earlier hypotheses on this level, all refuted (no level within the trial)")
        for t in tried:
            lines.append(f"- {t['hypothesis']} (its plan named {t['named']}; {t['note']})")
    lines.append("\n## The frame now")
    lines += hexrows(g)
    return "\n".join(lines)
