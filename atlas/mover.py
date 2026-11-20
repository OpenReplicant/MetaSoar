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
    def __init__(self, names, seed=0, explore=30, simulate=False, horizon=20):
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
        self.deaths = []  # (step, attempt, "pit" or "harm", world column): what each lost life is blamed on
        # the self-motion simulator (P2, docs/cognitive-model.md): how self's velocity changes a step under each
        # action, from the ground or the air, learned from every step; a macro is simulated against the pits before it
        # runs, and each prediction is scored against what happened (surprise)
        self.simulate, self.horizon = simulate, horizon
        self.dyn_x = collections.defaultdict(list)  # (action, vx) -> next vx; (action,) -> any
        self.dyn_y = collections.defaultdict(list)  # (action, held, grounded, vy) -> next vy; (action, grounded) -> any
        self.vel = None  # self's velocity over the last step
        self.open = []  # predictions being scored: {"start", "pred", "actual"}
        self.surprise = collections.deque(maxlen=200)  # mean pixel error of finished predictions
        self.ground_y = {}  # (area, column) -> self's y when standing there
        self.grounded, self.was_grounded, self.prev_action, self.held, self.was_still = True, True, None, 0, True

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
            gone = int(self.self_c[0]) // 16
            lo, hi = sorted((col + (1 if gone >= col else -1), gone))
            self.pits[area].update(range(lo, hi + 1) if hi - lo <= 4 else {col + 1, col + 2})
            self.deaths.append((self.t, self.attempt, "pit", gone))
            return
        self.deaths.append((self.t, self.attempt, "harm", None if self.self_c is None else int(self.self_c[0]) // 16))
        for t, kinds in self.near_log:
            if dt - 6 <= t <= dt + 1:
                for k in kinds:
                    self.harm[k] += 1

    # --- the self-motion simulator (P2) ---------------------------------------------------------------------
    @staticmethod
    def _mean(xs):
        return sum(xs) / len(xs) if xs else None

    def learn_motion(self, a, held, grounded, v0, v1):
        """One step of self's motion: velocity v0 (pixels a step, from the step before) became v1 under action a,
        held for `held` steps before this one (how long a jump is held shapes it; at the top of an arc the speed
        alone can't tell rising from falling)."""
        held = min(held, 6)
        self.dyn_y[(a, held, grounded, round(v0[1]))].append(v1[1])
        self.dyn_y[(a, held, grounded)].append(v1[1])
        self.dyn_y[(a, grounded)].append(v1[1])
        self.dyn_x[(a, round(v0[0]))].append(v1[0])
        self.dyn_x[(a,)].append(v1[0])

    def next_velocity(self, a, held, grounded, v):
        """The simulator's step: the mean of what followed the same action from the same state; nearest learned
        vertical speed when this one is new; the action's overall mean when nothing nearer is known."""
        held = min(held, 6)
        vy = self._mean(self.dyn_y.get((a, held, grounded, round(v[1])), []))
        if vy is None:
            near = [k for k in self.dyn_y if len(k) == 4 and k[:3] == (a, held, grounded)]
            if near:
                k = min(near, key=lambda k: abs(k[3] - v[1]))
                if abs(k[3] - v[1]) <= 3:
                    vy = self._mean(self.dyn_y[k])
        if vy is None:
            vy = self._mean(self.dyn_y.get((a, held, grounded), []))
        if vy is None:
            vy = self._mean(self.dyn_y.get((a, grounded), [])) or 0.0
        vx = self._mean(self.dyn_x.get((a, round(v[0])), []))
        if vx is None:
            vx = self._mean(self.dyn_x.get((a,), [])) or 0.0
        return vx, vy

    def rollout(self, actions):
        """Self's simulated path under these actions from now, on flat ground at its current height except over the
        known pits: [(dx, dy, grounded, over_pit)] per step; stops in a pit (falling below standing height over one)."""
        if self.self_c is None or self.vel is None:
            return []
        cx = self.self_c[0]
        pits = self.pit_columns()
        x = y = 0.0
        v, grounded, prev, held = self.vel, self.grounded, self.last_action, self.held
        out = []
        for a in actions:
            held = held + 1 if a == prev else 0
            v = self.next_velocity(a, held, grounded, v)
            prev = a
            x, y = x + v[0], y + v[1]
            col = int(cx + x) // 16
            over = col in pits
            if y >= 0 and not over:
                y, grounded, v = 0.0, True, (v[0], 0.0)
            else:
                grounded = False
            out.append((x, y, grounded, over))
            if over and y > 8:
                break
        return out

    def pit_columns(self):
        """The pits here, less any column self has stood on (a fall's start is only known to a column or so)."""
        stood = {c for a, c in self.ground_y if a == self.area}
        return self.pits[self.area] - stood

    def plan(self, macro):
        a, k = macro
        rest = self.rest()
        acts = ([rest] if k >= 6 and rest != a else []) + [a] * k
        return acts + [rest] * max(0, self.horizon - len(acts))

    def judge_path(self, macro):
        """What the simulator expects of this macro, against the pits within reach: "falls" (the path drops into
        one), "clears" (it passes every pit ahead and stands beyond), or None (no pit in reach, or no prediction)."""
        if self.self_c is None or self.vel is None or len(self.dyn_x) < 4:
            return None
        cx = self.self_c[0]
        fwd = self.forward_sign()
        ahead = {c for c in self.pit_columns() if 0 <= (c * 16 + 8 - cx) * fwd <= 96}
        if not ahead:
            return None
        path = self.rollout(self.plan(macro))
        if any(over and y > 8 for _, y, _, over in path):
            return "falls"
        far = max(ahead) if fwd > 0 else min(ahead)
        if any(g and (int(cx + x) // 16 - far) * fwd > 0 for x, _, g, _ in path):
            return "clears"
        return None

    def trace(self):
        """Score the open predictions against where self went (surprise), step by step while they last."""
        keep = []
        for tr in self.open:
            if self.self_c is None:
                continue
            i = len(tr["actual"])
            tr["actual"].append((self.self_c[0] - tr["start"][0], self.self_c[1] - tr["start"][1]))
            if i + 1 >= len(tr["pred"]):
                n = len(tr["actual"])
                err = sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(tr["pred"][:n], tr["actual"])) / max(1, n)
                self.surprise.append(err)
            else:
                keep.append(tr)
        self.open = keep

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
            if self.simulate:
                verdict = self.judge_path(m)
                if verdict == "falls":
                    v -= 200.0
                elif verdict == "clears":
                    v += 40.0
            scored.append((v + self.rng.random() * 0.01, m))
        v, m = max(scored)

        tried = self.q[key][m][1] if col is not None else 0
        self.why = (f"{sit[0]}{', blocked' if sit[1] else ''}{', pit ' + sit[2] if sit[2] != 'none' else ''}: "
                    f"{self.names[m[0]]} x{m[1]}"
                    f" ({'untried here' if not tried else f'{v:.0f} here'}{', frontier' if front else ''})")
        verdict = self.judge_path(m) if self.simulate else None
        if verdict:
            self.why += f", simulated: {verdict}"
        return m

    def step(self, obs):
        things = sorted(obs.get("things") or [], key=lambda th: th["id"])  # the order they came in can't matter
        cam = obs.get("camera") or {"area": 0, "x": 0}
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
                    v1 = (c[0] - pv[0], c[1] - pv[1])
                    if self.vel is not None:
                        self.learn_motion(self.last_action, self.held, self.was_grounded, self.vel, v1)
                    self.vel = v1
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
            still = self.prev_y is not None and abs(cy - self.prev_y) < 0.5
            self.grounded = still and self.was_still  # two still steps: at the top of a jump only one is
            self.was_still = still
            if self.grounded:  # standing on something
                self.last_ground = (area, col)
                self.ground_y[(area, col)] = cy
            self.prev_y = cy
            self.frontier[area] = max(self.frontier[area], col)
        if self.cur is not None:
            self.cur["ret"] += r
        self.trace()
        if loss:
            self.open, self.vel = [], None
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
            if self.simulate and me is not None and self.grounded and len(self.dyn_x) >= 4:
                pred = [(x, y) for x, y, _, _ in self.rollout(self.queue)][:len(self.queue)]
                if pred:
                    self.open.append({"start": self.self_c, "pred": pred, "actual": []})
        a = self.queue.pop(0)
        self.prev = {th["id"]: self.centre(th) for th in things}
        self.prev_action, self.was_grounded = self.last_action, self.grounded
        self.held = self.held + 1 if a == self.last_action else 0  # steps this action was already held
        self.last_action = a
        self.t += 1
        return self.names[a], None

    def posts(self):
        """Claims for a workspace: which thing is self, the pits, the harmful kinds (each only when it changes)."""
        out, now = [], {"self": self.self_id, "pits": {a: sorted(c) for a, c in self.pits.items()},
                        "harm": dict(self.harm.most_common(8))}
        last = getattr(self, "_posted", {})
        if now["self"] != last.get("self"):
            out.append({"key": "claim:self", "kind": "claim", "salience": 0.5, "attrs": {"thing": now["self"]}})
        if now["pits"] != last.get("pits"):
            out.append({"key": "claim:pits", "kind": "claim", "salience": 0.8, "attrs": {"columns": now["pits"]}})
        if now["harm"] != last.get("harm"):
            out.append({"key": "claim:harm", "kind": "claim", "salience": 0.8, "attrs": {"kinds": now["harm"]}})
        self._posted = now
        return [e | {"source": "mover"} for e in out]

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

