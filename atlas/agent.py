"""The atlas prototype's first tier: claims learned from play, with no model calls (docs/atlas.md, "The first
experiment"). Nothing here knows any particular game.

Each step it reads the frame as objects (MetaSoar's perception: one-colour regions, ticking cells left out), works
out what the last action did, and records it as evidence for claims:
- **passable colours**: a colour the player's body moved onto passes; one it was stopped by, and that nothing has
  shown to pass, blocks;
- **what contact does**, per kind of object (colour and size): `take` (it vanished), `event` (the scene changed
  besides what moved), `harm` (the attempt ended or the player was sent back to its start), `level`, `block`,
  `none`;
- **what clicking does**, per kind of object, the same outcomes;
- **the player**: the kind the plain actions move most, how far each action moves it, and the kinds that move along
  with it (its body).

It chooses, in order:
1. **Test what is untested** (after EMPA): the nearest object, by a route over colours believed passable (an
   untried colour counts as passable: optimism, after WorldCoder), whose kind has never been touched, then one
   whose kind did something (take, event, level) and has not been touched since the scene last changed, then the
   rest. Kinds that harmed are avoided. For clicks, the same order over objects to click.
2. **When every object has been tested in this scene** and nothing won, the scene counts as new again: touching
   again may do something else (a switch's second press).
3. **Otherwise explore the map of scenes**: an action not yet tried in this scene, else the known way to the nearest
   scene with one, else any action not known to end the attempt.
"""
from __future__ import annotations

import collections
import importlib.util
import random
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "metasoar_perception", Path(__file__).resolve().parent.parent / "agent" / "perception" / "main.py")
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

GOAL_MAX = 256  # objects larger than this are floors and walls, not things to test
MAX_CLICKS = 24


def key(o):
    return (o["color"], o["size"], o["cx"], o["cy"])


def kind(o):
    return (o["color"], o["size"])


class Atlas:
    def __init__(self, names, takes_point, seed=0):
        self.names = names
        self.point = {n for i, n in enumerate(names) if takes_point(i)}
        self.plain = [n for n in names if n not in self.point]
        self.rng = random.Random(seed)
        self.prev = None
        self.masked = None
        self.last = None  # (action name, params or None, action key)
        # claims, as evidence counts
        self.passable = collections.defaultdict(lambda: [0, 0])  # colour -> [passed, blocked]
        self.contact = collections.defaultdict(collections.Counter)  # kind -> outcomes
        self.clicked = collections.defaultdict(collections.Counter)  # kind -> outcomes
        self.moves = collections.Counter()  # kind -> plain steps it moved on
        self.step_of = collections.defaultdict(collections.Counter)  # (action, kind) -> Counter of (dx, dy)
        self.along = collections.Counter()  # kind -> steps it moved with the player, by the same amount
        # per scene epoch (a new epoch when the scene changes besides what moved, or when all is tested)
        self.epoch = 0
        self.tested = set()  # (epoch, object key)
        self.stuck = set()  # (epoch, x, y, dx, dy): body moves that went nowhere
        # the map of scenes
        self.tried = collections.defaultdict(set)
        self.dead = collections.defaultdict(set)
        self.fatal = collections.defaultdict(set)
        self.edges = collections.defaultdict(dict)
        self.home = None
        self.target = None  # the object it is heading for, kept while untested and reachable
        self.dead_pts = set()  # (level, x, y): points whose click did nothing
        self.why = ""

    # --- perception ---
    def perceive(self, obs):
        g = np.asarray(obs["frame"], dtype=np.int64)
        if self.masked is None or self.masked.shape != g.shape:
            self.masked = np.zeros(g.shape, dtype=bool)
        _, objs = P.objects(g)
        objs = [o for o in objs if not self.masked[o["y"]:o["y"] + o["h"], o["x"]:o["x"] + o["w"]].all()]
        for i, o in enumerate(objs):
            o["id"] = i
        return g, objs

    def mover(self):
        if not self.moves:
            return None
        return max(self.moves.items(), key=lambda kv: (kv[1], kv[0][1]))[0]

    def vec(self, action, mk):
        c = self.step_of.get((action, mk))
        if not c:
            return None
        v = max(c, key=c.get)
        return v if v != (0, 0) else None

    def body(self, objs, mk):
        me = next((o for o in objs if kind(o) == mk), None)
        if me is None:
            return None, None
        x0, y0, x1, y1 = me["x"], me["y"], me["x"] + me["w"] - 1, me["y"] + me["h"] - 1
        for o in objs:
            if o is not me and self.along[kind(o)] >= 2 and o["x"] <= x1 + 1 and o["x"] + o["w"] >= x0 \
                    and o["y"] <= y1 + 1 and o["y"] + o["h"] >= y0:
                x0, y0 = min(x0, o["x"]), min(y0, o["y"])
                x1, y1 = max(x1, o["x"] + o["w"] - 1), max(y1, o["y"] + o["h"] - 1)
        return me, (x0, y0, x1, y1)

    # --- learning from the last step ---
    def learn(self, g, objs, obs):
        pv = self.prev
        name, params, akey = self.last
        pg, pobjs = pv["g"], pv["objs"]
        changed = g != pg
        moved = P.moved_objects(objs[:MAX_CLICKS], pobjs)
        rest = changed.copy()
        for m in moved:
            o = objs[m["id"]]
            for bx, by in ((o["x"], o["y"]), (o["x"] - m["dx"], o["y"] - m["dy"])):
                rest[max(by, 0):max(by + o["h"], 0), max(bx, 0):max(bx + o["w"], 0)] = False
        ry, rx = np.nonzero(rest)
        if 0 < len(ry) <= 2 and not self.masked[ry, rx].all():  # a tick: leave its region out from now on
            for y, x in zip(ry.tolist(), rx.tolist()):
                if not self.masked[y, x]:
                    y0, x0, y1, x1 = P.region_box(pg, y, x)
                    self.masked[y0:y1 + 1, x0:x1 + 1] = True
            pv["state"] = P.signature(pg, self.masked)
        event = int((rest & ~self.masked).sum()) > 2
        lost = obs.get("attempt", 1) > pv["attempt"]
        level = obs.get("levels_completed", 0) > pv["levels"]
        state = P.signature(g, self.masked)

        # the player
        if params is None:
            for m in moved:
                self.moves[kind(m)] += 1
                self.step_of[(name, kind(m))][(m["dx"], m["dy"])] += 1
        mk = self.mover()
        outcome, contacts = None, []
        if mk is not None and params is None:
            pm = next((m for m in moved if kind(m) == mk), None)
            if pm is not None:
                for m in moved:
                    if kind(m) != mk and (m["dx"], m["dy"]) == (pm["dx"], pm["dy"]):
                        self.along[kind(m)] += 1
            v = self.vec(name, mk)
            _, box = self.body(pobjs, mk)
            if v and box:
                x0, y0, x1, y1 = box
                dx0, dy0, dx1, dy1 = x0 + v[0], y0 + v[1], x1 + v[0], y1 + v[1]
                H, W = g.shape
                inside = 0 <= dx0 and 0 <= dy0 and dx1 < W and dy1 < H
                dest = pg[max(dy0, 0):dy1 + 1, max(dx0, 0):dx1 + 1]
                own = set(pg[y0:y1 + 1, x0:x1 + 1].ravel().tolist())
                went = pm is not None and (pm["dx"], pm["dy"]) == v
                here = next((o for o in objs if kind(o) == mk), None)
                sent_home = pm is not None and not went and here is not None and self.home is not None \
                    and (here["cx"], here["cy"]) == self.home
                if went and not lost and not level:
                    for c in set(dest.ravel().tolist()):
                        self.passable[c][0] += 1
                elif pm is None and not lost and not level and inside:
                    self.stuck.add((self.epoch, x0, y0, v[0], v[1]))
                    blame = [c for c in set(dest.ravel().tolist()) - own if self.passable[c][0] == 0]
                    for c in blame:
                        self.passable[c][1] += 1
                # what the body touched: objects whose box meets the destination, grown by one cell
                ex0, ey0, ex1, ey1 = dx0 - 1, dy0 - 1, dx1 + 1, dy1 + 1
                gone = {key(o) for o in pobjs} - {key(o) for o in objs}
                for o in pobjs:
                    k = kind(o)
                    if k == mk or self.along[k] >= 2 or o["size"] > GOAL_MAX:
                        continue
                    if o["x"] <= ex1 and o["x"] + o["w"] - 1 >= ex0 and o["y"] <= ey1 and o["y"] + o["h"] - 1 >= ey0:
                        contacts.append(o)
                if level:
                    outcome = "level"
                elif lost or sent_home:
                    outcome = "harm"
                elif any(key(o) in gone for o in contacts):
                    outcome = "take"
                elif event:
                    outcome = "event"
                elif pm is None:
                    outcome = "block"
                else:
                    outcome = "none"
                for o in contacts:
                    out = outcome if outcome != "take" or key(o) in gone else "none"
                    self.contact[kind(o)][out] += 1
                    self.tested.add((self.epoch, key(o)))
        hit = None
        if params is not None:
            x, y = params["x"], params["y"]
            hit = next((o for o in pobjs if o["x"] <= x < o["x"] + o["w"] and o["y"] <= y < o["y"] + o["h"]
                        and pg[y, x] == o["color"]), None)
            outcome = "level" if level else "harm" if lost else "event" if (event or moved) else "none"
            if hit is not None:
                self.clicked[kind(hit)][outcome] += 1
                self.tested.add((self.epoch, key(hit)))

        # the map of scenes
        f = pv["state"]
        self.tried[f].add(akey)
        if lost:
            self.fatal[f].add(akey)
        elif state == f:
            self.dead[f].add(akey)
        else:
            self.edges[f][akey] = state

        if level:
            self.stuck.clear()
            self.home = None
        if event or level or lost:
            self.epoch += 1
            if event and not (level or lost):
                # what it touched or clicked made the change: that stays tested in the new scene
                for o in contacts + ([hit] if params is not None and hit is not None else []):
                    self.tested.add((self.epoch, key(o)))
        if params is not None and not (event or moved or level or lost):
            self.dead_pts.add((obs.get("levels_completed", 0), params["x"], params["y"]))
        return state, lost or level

    # --- choosing ---
    def actions(self, objs):
        acts = [(n, None, n) for n in self.plain]
        for n in sorted(self.point):
            for o in objs[:MAX_CLICKS]:
                acts.append((n, {"x": o["cx"], "y": o["cy"]}, f"{n}@{o['cx']},{o['cy']}"))
        return acts

    def harmful(self, outcomes):
        return outcomes["harm"] > 0 and outcomes["harm"] >= outcomes["take"] + outcomes["event"] + outcomes["level"]

    def tier(self, outcomes):
        if not outcomes:
            return 0  # never tested
        if outcomes["take"] or outcomes["event"] or outcomes["level"]:
            return 1  # did something
        return 2

    def testable(self, objs, g):
        H, W = g.shape
        mk = self.mover()
        return [o for o in objs if o["size"] <= GOAL_MAX and kind(o) != mk and self.along[kind(o)] < 2
                and o["x"] > 0 and o["y"] > 0 and o["x"] + o["w"] < W and o["y"] + o["h"] < H]

    def route(self, g, objs, box, mk, targets):
        """Breadth-first over where the body can stand, by the moves it knows, over colours believed passable.
        Returns (first action, steps, target) for the nearest target in the best tier, or None."""
        vecs = {}
        for a in self.plain:
            v = self.vec(a, mk)
            if v and v not in vecs.values():
                vecs[a] = v
        if len(vecs) < 2:
            return None
        H, W = g.shape
        free = np.ones(g.shape, dtype=bool)
        for c, (passed, blocked) in self.passable.items():
            if passed == 0 and blocked > 0:
                free[g == c] = False
        for o in objs:
            if self.harmful(self.contact[kind(o)]):
                free[o["y"]:o["y"] + o["h"], o["x"]:o["x"] + o["w"]] = False
        x0, y0, x1, y1 = box
        free[y0:y1 + 1, x0:x1 + 1] = True
        for o in targets:
            free[o["y"]:o["y"] + o["h"], o["x"]:o["x"] + o["w"]] = True
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        ii = np.zeros((H + 1, W + 1), dtype=np.int64)
        ii[1:, 1:] = (~free).cumsum(0).cumsum(1)

        def ok(x, y):
            return 0 <= x and 0 <= y and x + bw <= W and y + bh <= H and \
                ii[y + bh, x + bw] - ii[y, x + bw] - ii[y + bh, x] + ii[y, x] == 0

        def touching(x, y):
            out = []
            for o in targets:
                if o["x"] <= x + bw and o["x"] + o["w"] - 1 >= x - 1 and o["y"] <= y + bh and o["y"] + o["h"] - 1 >= y - 1:
                    out.append(o)
            return out

        first = {(x0, y0): None}
        frontier, d, best = [(x0, y0)], 0, None
        while frontier and len(first) < 600:
            d += 1
            nxt = []
            for x, y in frontier:
                for a, v in vecs.items():
                    n = (x + v[0], y + v[1])
                    if n in first or (self.epoch, x, y, v[0], v[1]) in self.stuck or not ok(*n):
                        continue
                    first[n] = first[(x, y)] or a
                    nxt.append(n)
                    for o in touching(*n):
                        cand = (self.tier(self.contact[kind(o)]) - (key(o) == self.target) * 3, d, first[n], o)
                        if best is None or cand[:2] < best[:2]:
                            best = cand
            if best is not None and best[0] <= 0:
                break
            frontier = nxt
        return None if best is None else (best[2], best[1], best[3])

    def choose(self, g, objs, state):
        mk = self.mover()
        acts = self.actions(objs)
        fatal = self.fatal[state]
        # 1. touch what is untested, by a route
        if mk is not None:
            me, box = self.body(objs, mk)
            if me is not None:
                if self.home is None:
                    self.home = (me["cx"], me["cy"])
                for again in (False, True):
                    targets = [o for o in self.testable(objs, g) if (self.epoch, key(o)) not in self.tested
                               and not self.harmful(self.contact[kind(o)])]
                    if targets:
                        r = self.route(g, objs, box, mk, targets)
                        if r is not None and r[0] not in fatal:
                            self.target = key(r[2])
                            self.why = f"touch {kind(r[2])} t{self.tier(self.contact[kind(r[2])])} in {r[1]}"
                            return r[0], None, r[0]
                        break
                    if again or not self.testable(objs, g):
                        break
                    self.epoch += 1  # everything tested here and nothing won: touching again may differ
        # 1'. a click not yet tried in this scene, never one that did nothing on this level (in any scene): a kind
        # never clicked first, then any at random
        if self.point:
            lv = self.prev["levels"] if self.prev else 0
            cands = []
            for n, p, k in acts:
                if p is None or k in fatal or k in self.tried[state] or (lv, p["x"], p["y"]) in self.dead_pts:
                    continue
                o = next((o for o in objs if o["cx"] == p["x"] and o["cy"] == p["y"]), None)
                if o is None or self.harmful(self.clicked[kind(o)]):
                    continue
                cands.append((0 if not self.clicked[kind(o)] else 1, n, p, k))
            if cands:
                t = min(c[0] for c in cands)
                _, n, p, k = self.rng.choice([c for c in cands if c[0] == t])
                self.why = f"click t{t}"
                return n, p, k
        # 2. an action not tried in this scene
        lv = self.prev["levels"] if self.prev else 0
        fresh = [a for a in acts if a[2] not in self.tried[state] and a[2] not in fatal
                 and (a[1] is None or (lv, a[1]["x"], a[1]["y"]) not in self.dead_pts)]
        if fresh:
            self.why = "fresh"
            return self.rng.choice(fresh)
        # 3. the known way to the nearest scene with something untried
        prev, q, seen = {}, collections.deque([state]), {state}
        while q:
            s = q.popleft()
            if s != state and (any(a[2] not in self.tried[s] for a in acts) or s not in self.tried):
                while prev[s][0] != state:
                    s = prev[s][0]
                k = prev[s][1]
                for a in acts:
                    if a[2] == k:
                        self.why = "toward untried"
                        return a
                break
            for k, t in self.edges[s].items():
                if t not in seen and k not in self.fatal[s]:
                    seen.add(t)
                    prev[t] = (s, k)
                    q.append(t)
        if self.point:
            lv = self.prev["levels"] if self.prev else 0
            for _ in range(20):
                x, y = self.rng.randrange(g.shape[1]), self.rng.randrange(g.shape[0])
                if (lv, x, y) not in self.dead_pts:
                    n = sorted(self.point)[0]
                    self.why = "point"
                    return n, {"x": x, "y": y}, f"{n}@{x},{y}"
        safe = [a for a in acts if a[2] not in fatal and a[2] not in self.dead[state]] or acts
        self.why = "any"
        return self.rng.choice(safe)

    def step(self, obs):
        g, objs = self.perceive(obs)
        if self.prev is not None and self.last is not None:
            state, reset = self.learn(g, objs, obs)
        else:
            state, reset = P.signature(g, self.masked), True
        if self.prev is not None and obs.get("attempt", 1) > self.prev["attempt"]:
            self.home = None
        name, params, akey = self.choose(g, objs, state)
        self.prev = {"g": g, "objs": objs, "state": state, "attempt": obs.get("attempt", 1),
                     "levels": obs.get("levels_completed", 0)}
        self.last = (name, params, akey)
        return name, params
