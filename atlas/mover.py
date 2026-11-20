"""The atlas for scenes that move on their own (a platformer, say): claims learned from play, from tracked things
(envkit's `sight`: ids, kinds, world boxes, velocities) instead of a still grid. Nothing here knows any game, or what
an action's name means.

Claims, each from evidence:
- **self**: the tracked thing whose motion follows the actions (the largest spread of mean motion between actions);
  afterwards any thing showing one of self's pictures, nearest to where self was.
- **what each action does** to self: mean (dx, dy) while held.
- **what pays**: the reward each held action earned, per place (area, 16-pixel column) and per situation (a threat
  near, blocked), so what was learned in one place is tried first in a similar one.
- **what harms**: kinds of things near self in the steps before a life is lost.
- **pits**: where self went out through the bottom of the view; "a pit this far ahead" is part of the situation, so
  what worked before one pit is tried first before the next.

It acts in **macros**: one action held for a few steps. Only actions that lift self (jumps) are held long, with a
step of a non-lifting action first so the button counts as a new press; the rest are held two steps and chosen again.
It chooses the macro with the best value where it is plus a bonus for the less tried (UCB), trying untried ones
first at the furthest place it has reached, and where it has never acted in a place, by the situation. A loss is
blamed on the macros running when self last looked normal: the game reports the loss only after its death scene.
"""
from __future__ import annotations

import collections
import random

HOLDS = (2, 6, 12)
LOSS = -150.0  # a lost life, in reward units
THREAT = (56, 40)  # how near (x, y in pixels) a harmful or unknown moving thing counts as a threat


class Mover:
    def __init__(self, names, seed=0, explore=30):
        self.names, self.rng = list(names), random.Random(seed)
        self.macros = [(a, k) for a in range(len(names)) for k in HOLDS]
        self.queue, self.cur, self.why = [], None, "start"
        self.t, self.explore = 0, explore
        self.track_dx = collections.defaultdict(lambda: collections.defaultdict(list))  # id -> action -> dx
        self.self_id, self.self_kinds, self.self_c = None, collections.Counter(), None
        self.self_px = []  # self's size in pixels, each step it was seen
        self.prev_self_kind, self.strange = None, 0  # self's picture last step; steps in a row it looked unlike self
        self.effect = collections.defaultdict(list)  # action -> [(dx, dy)]
        self.q = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0]))  # place -> macro -> [sum, n]
        self.g = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0]))  # situation -> macro
        self.harm = collections.Counter()  # kind -> lives lost near it
        self.pits = collections.defaultdict(set)  # area -> world columns (16 px) where self fell out of view
        self.view_bottom = 0  # the lowest any thing has been seen: the bottom of the view
        self.near_log = collections.deque(maxlen=120)  # (step, kinds near self)
        self.prev, self.attempt, self.frontier = None, 1, collections.defaultdict(lambda: -1)
        self.last_action = None
        self.last_ground, self.prev_y, self.area = (0, 0), None, 0
        self.rew = collections.defaultdict(list)  # action -> reward each step it was held
        self.history = collections.deque(maxlen=40)  # settled macros: (start, end, q key, situation, macro)
        self.normal_t = 0  # the last step self showed one of its usual pictures: alive and in control

    # --- perception ------------------------------------------------------------------------------------------
    @staticmethod
    def centre(th):
        b = th["box"]
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2

    def find_self(self, things):
        if self.self_id is not None:
            for th in things:
                if th["id"] == self.self_id:
                    return th
        cands = [th for th in things if self.self_kinds[th["kind"]] >= 3]
        if not cands:
            return None
        c = self.self_c or (0, 0)
        th = max(cands, key=lambda th: (self.self_kinds[th["kind"]],
                                        -abs(self.centre(th)[0] - c[0]) - abs(self.centre(th)[1] - c[1])))
        self.self_id = th["id"]
        return th

    def like_self(self, th):
        """About self's size: a merged blob or a stranger is not taken as one of self's pictures."""
        if len(self.self_px) < 5:
            return True
        med = sorted(self.self_px[-200:])[len(self.self_px[-200:]) // 2]
        return 0.5 * med <= th["px"] <= 2.5 * med

    def identify(self, things):
        """Self is the track whose mean motion differs most between actions, among tracks seen most of the time
        (an enemy passing through is seen briefly and its motion doesn't follow the actions)."""
        best, score = None, 0.0
        for tid, per in self.track_dx.items():
            if sum(len(v) for v in per.values()) < 0.6 * self.t:
                continue
            means = [sum(v) / len(v) for v in per.values() if len(v) >= 3]
            if len(means) >= 2 and max(means) - min(means) > score:
                best, score = tid, max(means) - min(means)
        if best is not None and score >= 2:
            self.self_id = best
            for th in things:
                if th["id"] == best:
                    self.self_kinds[th["kind"]] += 3

    # --- learning --------------------------------------------------------------------------------------------
    def place(self, me, cam):
        return (cam["area"], int(self.centre(me)[0]) // 16) if me else (cam["area"], None)

    def where(self, place, sit):
        """The key for what pays here: the place and whether a threat is near (an enemy changes what works)."""
        return place + (sit[0], sit[2])

    def situation(self, me, things, blocked):
        if not me:
            return ("lost", blocked, "none")
        cx, cy = self.centre(me)
        fwd = self.forward_sign()
        threat = False
        for th in things:
            if th["id"] == me["id"] or not th.get("moved"):
                continue
            x, y = self.centre(th)
            if 0 <= (x - cx) * fwd <= THREAT[0] and abs(y - cy) <= THREAT[1] and (self.harm[th["kind"]] or th["kind"] not in self.safe_kinds()):
                threat = True
        ahead = [(c * 16 - cx) * fwd for c in self.pits[self.area] if 0 <= (c * 16 - cx) * fwd <= 96]
        pit = "none" if not ahead else ("<16" if min(ahead) < 16 else "<40" if min(ahead) < 40 else "<96")
        return ("threat" if threat else "clear", blocked, pit)

    def safe_kinds(self):
        return {k for k, n in self.self_kinds.items() if n >= 3}

    def forward_sign(self):
        """The direction that pays: the sign of the dx of the action that earned the most reward a step."""
        best, val = 1, None
        for a in range(len(self.names)):
            e = self.effect[a]
            if len(e) < 3:
                continue
            dx = sum(d for d, _ in e) / len(e)
            r = self.reward_rate.get(a)
            if r is not None and abs(dx) > 0.5 and (val is None or r > val):
                best, val = (1 if dx > 0 else -1) * (1 if r >= 0 else -1), r
        return best

    def settle(self, loss):
        """Close the macro just finished: credit its reward (and a loss) to its place and situation."""
        if self.cur is None:
            return
        place, sit, macro, ret = self.cur["place"], self.cur["sit"], self.cur["macro"], self.cur["ret"]
        if loss:
            ret += LOSS
        for table, key in ((self.q, self.where(place, sit)), (self.g, sit)):
            cell = table[key][macro]
            cell[0] += ret
            cell[1] += 1
        self.history.append((self.cur["t0"], self.t, self.where(place, sit), sit, macro))
        self.cur = None

    def blame(self):
        """A life was lost: the loss goes to the macros running in the few steps before self last looked normal
        (the game says a life is lost only after its death scene), and the kinds near self then are harmful."""
        dt = self.normal_t
        for t0, t1, key, sit, macro in self.history:
            if t0 <= dt + 1 and t1 >= dt - 14:  # a fall starts with the step off the edge, ~10 steps before
                self.q[key][macro][0] += LOSS
                self.g[sit][macro][0] += LOSS
        fell = self.self_c is not None and self.self_c[1] >= self.view_bottom - 24
        if fell:  # a pit: self went out through the bottom; it starts where self last stood
            area, col = self.last_ground
            self.pits[area].update({col + 1, col + 2})
            return
        for t, kinds in self.near_log:
            if dt - 6 <= t <= dt + 1:
                for k in kinds:
                    self.harm[k] += 1

    # --- choosing --------------------------------------------------------------------------------------------
    def value(self, table, key, m, optimistic, bonus=30.0):
        """The mean return, plus a bonus that shrinks as the macro is tried more here (UCB): where everything
        earns nothing, the least tried is tried next instead of the same one forever."""
        s, n = table[key][m]
        total = sum(c[1] for c in table[key].values())
        return s / n + bonus * ((1 + total) ** 0.5) / (1 + n) if n else optimistic

    def lifts(self, a):
        """Does this action carry self upward (a jump)? Only such actions are worth holding long: everything else
        is held for two steps and chosen again, so a run doesn't carry self past the place where it should act."""
        e = self.effect[a]
        return len(e) >= 3 and sum(dy for _, dy in e) / len(e) < -0.5

    def options(self):
        if self.t < self.explore:
            return self.macros
        return [(a, k) for a, k in self.macros if k == HOLDS[0] or self.lifts(a)]

    def choose(self, place, sit):
        area, col = place
        if self.t < self.explore:
            self.why = "finding myself" if self.self_id is None else "trying actions"
            return self.rng.choice(self.macros)
        key = self.where(place, sit)
        front = col is not None and col >= self.frontier[area]
        scored = []
        for m in self.options():
            if col is not None and self.q[key][m][1]:
                v = self.value(self.q, key, m, 0.0)
            elif self.g[sit][m][1]:  # never done here: what it earned in this situation elsewhere
                v = self.value(self.g, sit, m, 0.0, bonus=10.0)
            else:
                v = 60.0 if front else 15.0
            scored.append((v + self.rng.random() * 0.01, m))
        v, m = max(scored)
        tried = self.q[key][m][1] if col is not None else 0
        self.why = (f"{sit[0]}{', blocked' if sit[1] else ''}{', pit ' + sit[2] if sit[2] != 'none' else ''}: "
                    f"{self.names[m[0]]} x{m[1]}"
                    f" ({'untried here' if not tried else f'{v:.0f} here'}{', frontier' if front else ''})")
        return m

    def step(self, obs):
        things, cam = obs.get("things") or [], obs.get("camera") or {"area": 0, "x": 0}
        self.area = cam["area"]
        attempt = obs.get("attempt", 1)
        loss = attempt > self.attempt
        self.attempt = attempt
        r = float(obs.get("reward", 0) or 0)
        for th in things:
            self.view_bottom = max(self.view_bottom, th["box"][3])
        me = self.find_self(things)
        # evidence from the last step
        if self.prev is not None and self.last_action is not None:
            for th in things:
                pv = self.prev.get(th["id"])
                if pv is not None:
                    self.track_dx[th["id"]][self.last_action].append(self.centre(th)[0] - pv[0])
            if me and me["id"] in self.prev:
                pv = self.prev[me["id"]]
                c = self.centre(me)
                known = self.self_kinds[me["kind"]] >= 3
                jump = abs(c[0] - pv[0]) > 16 or abs(c[1] - pv[1]) > 16  # a restart, not a move
                if not jump and self.like_self(me) and (known or self.self_kinds[self.prev_self_kind] >= 3):
                    # a new picture joins self only straight after a known one, on the same track
                    self.effect[self.last_action].append((c[0] - pv[0], c[1] - pv[1]))
                    self.self_kinds[me["kind"]] += 1
                    self.self_px.append(me["px"])
                self.strange = 0 if known else self.strange + 1
        if me:
            self.prev_self_kind = me["kind"]
        if self.strange >= 3:  # the track wandered off onto something else
            self.self_id, self.strange = None, 0
            me = self.find_self(things)
        if self.last_action is not None:
            self.rew[self.last_action].append(r)
        if self.self_id is None and self.t >= 8:
            self.identify(things)
            me = self.find_self(things)
        if me:
            self.self_c = self.centre(me)
            cx, cy = self.self_c
            self.near_log.append((self.t, [th["kind"] for th in things if th["id"] != me["id"]
                                           and abs(self.centre(th)[0] - cx) <= 24 and abs(self.centre(th)[1] - cy) <= 24]))
            if self.self_kinds[me["kind"]] >= 10:
                self.normal_t = self.t
            area, col = self.place(me, cam)
            if self.prev_y is not None and abs(cy - self.prev_y) < 0.5:  # standing on something
                self.last_ground = (area, col)
            self.prev_y = cy
            self.frontier[area] = max(self.frontier[area], col)
        if self.cur is not None:
            self.cur["ret"] += r
        if loss:
            self.queue = []
            self.settle(loss=False)
            self.blame()
            self.self_id = None  # find self again after the restart, by its pictures
        if not self.queue:
            self.settle(loss=False)
            blocked = self.blocked()
            place, sit = self.place(me, cam), self.situation(me, things, blocked)
            m = self.choose(place, sit)
            self.cur = {"place": place, "sit": sit, "macro": m, "ret": 0.0, "start": self.self_c, "t0": self.t}
            a, k = m
            rest = self.rest()
            self.queue = ([rest] if k >= 6 and rest != a else []) + [a] * k
            self.last_macro_action = a
        a = self.queue.pop(0)
        self.prev = {th["id"]: self.centre(th) for th in things}
        self.last_action = a
        self.t += 1
        return self.names[a], None

    def rest(self):
        """One step before a long hold, so the held button counts as a new press: the last action if it doesn't
        lift (keep running), else the non-lifting action that pays best."""
        last = getattr(self, "last_macro_action", None)
        if last is not None and not self.lifts(last):
            return last
        ground = [a for a in range(len(self.names)) if not self.lifts(a)]
        rates = self.reward_rate
        return max(ground, key=lambda a: rates.get(a, 0.0)) if ground else 0

    @property
    def reward_rate(self):
        return {a: sum(v) / len(v) for a, v in self.rew.items() if len(v) >= 3}

    def blocked(self):
        """The last macro moved self less than a pixel a step though its action moves self forward."""
        if self.cur is None or self.cur["start"] is None or self.self_c is None:
            return False
        a, k = self.cur["macro"]
        e = self.effect[a]
        if len(e) < 3:
            return False
        dx = sum(d for d, _ in e) / len(e)
        return abs(dx) > 1 and abs(self.self_c[0] - self.cur["start"][0]) < k * 0.5

