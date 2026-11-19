"""The agent's perception (M-09): raw observations in, symbols out, one JSON line each way per step.

What it reports knows no particular game (each WME on the input link costs every step, so it reports only what the
rules read):
- for a grid of colours (an observation key holding a 2-D array larger than the adapter puts on the input link raw):
  `objects`, the connected regions of one colour (4-neighbour), except the grid's most common colour (the
  background), largest first, at most MAX_OBJECTS: id, color, size, cx, cy (the object's own cell nearest its
  centroid: a point on it to click, which moves with it)
- `moved`: objects that kept their colour and size but shifted since the last frame (dx, dy)
- `last-action`, and `last-x`, `last-y` for a point: what was just done
- `background`: that commonest colour
- `state`: a signature of the frame without its ticking cells, so the same scene gives the same symbol whatever a
  step counter or budget bar shows. A cell ticks when it changes on a step where at most two cells change besides
  those that what moved explains (its boxes, before and after); the region it belonged to (its bounding box, at its
  size before the tick) is left out of every signature from then on, and objects lying wholly in it are not
  reported.
- `mover`: the colour and size of what the plain actions (those without a point) move most often so far: what the
  player most likely controls; `at`: where it is, one symbol of colour, size and centre (the first such object);
  `was-at`: the same for the last frame; `reset`: the last plain action sent the mover back to where it was when the
  attempt began, by a jump that is not that action's usual step (progress thrown away)
- `goal-dx`, `goal-dy` (-1, 0 or 1): which way the nearest object the mover has not touched lies. Touching is the
  object's point coming within the mover's box (2 cells around it). Not counted: the mover's kind and kinds that move
  along with it, objects larger than GOAL_MAX cells (floors, walls) or touching the frame's edge (borders, panels), and goals given up (no closer in GOAL_PATIENCE
  steps; given up for the attempt). When the scene changes other than by what moved (something picked up, a switch),
  everything counts as untouched again, except what it touched on that step or the one before (the likely cause).
- `from`: the last step's `state`; `did`: the last step as one symbol, `from`-action, or `from`-action-x-y for a
  point, the same symbol the rules build for an action they propose; `act`, the same without the state; `lost`: the
  last action ended the attempt (the attempt count went up)
Between steps it keeps the last frame and objects, the cells it leaves out, the last signature, the attempt count
and how often each kind has moved after a plain action. The standard library and numpy (in the sandbox image with gymnasium).
"""
import hashlib
import json
import sys

import numpy as np

MAX_OBJECTS = 24
GOAL_MAX = 256
GOAL_PATIENCE = 15
SHOWN = ("id", "color", "size", "cx", "cy")  # of an object's fields, those the rules read


def grid_of(obs):
    for v in (obs or {}).values():
        if isinstance(v, list) and len(v) > 8 and isinstance(v[0], list) and len(v) * len(v[0]) > 1024:
            return np.asarray(v, dtype=np.int64)
    return None


def objects(g):
    """One-colour regions, 4-neighbour, from runs along each row joined to touching runs of the row above."""
    h, w = g.shape
    bg = int(np.bincount(g.ravel()).argmax())
    runs = []  # (y, x0, x1, colour)
    parent = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    above = []
    for y in range(h):
        row = g[y]
        cuts = np.flatnonzero(row[1:] != row[:-1]) + 1
        starts = [0, *cuts.tolist()]
        ends = [*(cuts - 1).tolist(), w - 1]
        here = []
        j = 0
        for x0, x1 in zip(starts, ends):
            c = int(row[x0])
            if c == bg:
                continue
            i = len(runs)
            runs.append((y, x0, x1, c))
            parent.append(i)
            here.append(i)
            while j < len(above) and runs[above[j]][2] < x0:
                j += 1
            k = j
            while k < len(above) and runs[above[k]][1] <= x1:
                if runs[above[k]][3] == c:
                    a, b = find(above[k]), find(i)
                    if a != b:
                        parent[max(a, b)] = min(a, b)
                k += 1
        above = here
    groups = {}
    for i, (y, x0, x1, c) in enumerate(runs):
        n = x1 - x0 + 1
        r = groups.setdefault(find(i), [c, 0, w, h, -1, -1, 0, 0])
        r[1] += n
        r[2], r[3], r[4], r[5] = min(r[2], x0), min(r[3], y), max(r[4], x1), max(r[5], y)
        r[6] += n * (x0 + x1) // 2  # the run's x's summed (n * (x0 + x1) is always even)
        r[7] += n * y
    # the point given for each object is one of its own cells, the nearest to its centroid (a ring's centre is not on it)
    near = {}
    for i, (y, x0, x1, c) in enumerate(runs):
        root = find(i)
        r = groups[root]
        mx, my = r[6] / r[1], r[7] / r[1]
        x = min(max(round(mx), x0), x1)
        d = (x - mx) ** 2 + (y - my) ** 2
        if root not in near or d < near[root][0]:
            near[root] = (d, x, y)
    out = [{"color": c, "size": n, "x": x0, "y": y0, "w": x1 - x0 + 1, "h": y1 - y0 + 1, "cx": near[k][1],
            "cy": near[k][2]} for k, (c, n, x0, y0, x1, y1, sx, sy) in groups.items()]
    # largest first; equal sizes in the order a row-by-row scan first meets them
    firsts = {}
    for i, (y, x0, x1, c) in enumerate(runs):
        firsts.setdefault(find(i), (y, x0))
    keyed = sorted(zip(groups.keys(), out), key=lambda t: (-t[1]["size"], firsts[t[0]]))
    out = [o for _, o in keyed]
    for i, o in enumerate(out):
        o["id"] = i
    return bg, out


def moved_objects(objs, prev):
    """Objects that kept colour and size but are somewhere else, matched to the nearest such object last frame."""
    still = {(p["color"], p["size"], p["x"], p["y"]) for p in prev}
    out = []
    for o in objs:
        if (o["color"], o["size"], o["x"], o["y"]) in still:
            continue
        cand = [p for p in prev if p["color"] == o["color"] and p["size"] == o["size"]]
        if cand:
            p = min(cand, key=lambda p: abs(p["x"] - o["x"]) + abs(p["y"] - o["y"]))
            out.append({"id": o["id"], "color": o["color"], "size": o["size"], "dx": o["x"] - p["x"], "dy": o["y"] - p["y"]})
    return out


def region_box(g, y, x):
    """The bounding box of the one-colour region holding cell (y, x)."""
    h, w = g.shape
    col = g[y, x]
    seen, stack = {(y, x)}, [(y, x)]
    while stack:
        cy, cx = stack.pop()
        for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
            if 0 <= ny < h and 0 <= nx < w and (ny, nx) not in seen and g[ny, nx] == col:
                seen.add((ny, nx))
                stack.append((ny, nx))
    ys, xs = [c[0] for c in seen], [c[1] for c in seen]
    return min(ys), min(xs), max(ys), max(xs)


def signature(g, masked):
    cells = np.where(masked, 255, g).astype(np.uint8)
    return "h" + hashlib.blake2b(cells.tobytes(), digest_size=6).hexdigest()


def route(g, free, start, vecs, wanted, stuck=(), limit=400):
    """Breadth-first over the places the mover's body can stand, stepping by the moves it knows. free: cells it may
    stand on; start: the body's box (x0, y0, x1, y1); wanted(x0, y0) -> the goal it touches there, or None. Returns
    {goal: (steps, {place: (move, steps left)} along the way)} for the goals it can reach."""
    H, W = g.shape
    ii = np.zeros((H + 1, W + 1), dtype=np.int64)
    ii[1:, 1:] = (~free).cumsum(0).cumsum(1)
    bw, bh = start[2] - start[0] + 1, start[3] - start[1] + 1

    def ok(x, y):
        return 0 <= x and 0 <= y and x + bw <= W and y + bh <= H and \
            ii[y + bh, x + bw] - ii[y, x + bw] - ii[y + bh, x] + ii[y, x] == 0

    back = {(start[0], start[1]): None}
    frontier, d, found = [(start[0], start[1])], 0, {}
    while frontier and len(back) < limit:
        d += 1
        nxt = []
        for x, y in frontier:
            for v in vecs:
                n = (x + v[0], y + v[1])
                if n not in back and (x, y, v) not in stuck and ok(*n):
                    back[n] = ((x, y), v)
                    nxt.append(n)
                    t = wanted(*n)
                    if t is not None and t not in found:
                        way, here, left = {}, n, 0
                        while back[here]:
                            here, v2 = back[here]
                            left += 1
                            way[here] = (v2, left)
                        found[t] = (d, way)
        frontier = nxt
    return found


def main():
    prev_grid, prev_objs, masked, prev_state, attempt = None, [], None, None, None
    moves = {}  # (colour, size) -> plain-action steps it moved on
    steps = {}  # (action, colour, size) -> {(dx, dy): count}
    first = None  # the objects of the attempt's first frame
    touched, given_up, along = set(), set(), set()  # objects by (colour, size, cx, cy); kinds that move with the mover
    goal, best, stale = None, None, 0
    prev_obs, recent, last_touch = None, set(), set()
    floor = set()  # colours the mover's body has stood on
    stuck, body = set(), None  # (x, y, move): where the body's move went nowhere, since the scene last changed
    way, way_for = {}, None  # the way planned to the goal, kept while the body keeps to it
    for line in sys.stdin:
        msg = json.loads(line)
        g = grid_of(msg.get("observation"))
        if g is None:
            print(json.dumps({}), flush=True)
            continue
        if masked is None or masked.shape != g.shape:
            masked = np.zeros(g.shape, dtype=bool)
        bg, objs = objects(g)
        # what lies wholly in the ticking cells (a budget bar, a counter) is not a thing to act on
        objs = [o for o in objs if not masked[o["y"]:o["y"] + o["h"], o["x"]:o["x"] + o["w"]].all()]
        for i, o in enumerate(objs):
            o["id"] = i
        res = {"background": bg, "count": len(objs),
               "objects": [{k: o[k] for k in SHOWN} for o in objs[:MAX_OBJECTS]]}
        if prev_grid is not None and prev_grid.shape == g.shape:
            changed = g != prev_grid
            moved = moved_objects(objs[:MAX_OBJECTS], prev_objs)
            res["moved"] = moved[:8]
            # what moved explains the cells in its boxes, before and after; at most two cells changed besides is a tick
            rest = changed.copy()
            for m in moved:
                o = objs[m["id"]]
                for bx, by in ((o["x"], o["y"]), (o["x"] - m["dx"], o["y"] - m["dy"])):
                    rest[max(by, 0):max(by + o["h"], 0), max(bx, 0):max(bx + o["w"], 0)] = False
            event = int((rest & ~masked).sum()) > 2
            ry, rx = np.nonzero(rest)
            if 0 < len(ry) <= 2 and not masked[ry, rx].all():
                # a tick: leave out the region it belonged to, at its size before the tick, and say again what the
                # last frame was without it, so a step that only ticked reads as going nowhere
                for y, x in zip(ry.tolist(), rx.tolist()):
                    if not masked[y, x]:
                        y0, x0, y1, x1 = region_box(prev_grid, y, x)
                        masked[y0:y1 + 1, x0:x1 + 1] = True
                prev_state = signature(prev_grid, masked)
        else:
            event = False
        state = signature(g, masked)
        res["state"] = state
        obs = msg.get("observation") or {}
        last = msg.get("last") or {}
        if last.get("action"):
            res["last-action"] = last["action"]
            params = last.get("params") or {}
            did = [last["action"]]
            if "x" in params and "y" in params:
                res["last-x"], res["last-y"] = int(params["x"]), int(params["y"])
                did += [str(res["last-x"]), str(res["last-y"])]
            if prev_state is not None:
                res["from"] = prev_state
                res["did"] = "-".join([prev_state] + did)
            res["act"] = "-".join(did)
            if "last-x" not in res:
                for kind in {(m["color"], m["size"]) for m in res.get("moved", [])}:
                    moves[kind] = moves.get(kind, 0) + 1
                for m in res.get("moved", []):
                    d = steps.setdefault((last["action"], m["color"], m["size"]), {})
                    d[(m["dx"], m["dy"])] = d.get((m["dx"], m["dy"]), 0) + 1
            if attempt is not None and obs.get("attempt", attempt) > attempt:
                res["lost"] = "yes"
        if moves:
            (c, z), _ = max(moves.items(), key=lambda kv: (kv[1], kv[0][1]))
            res["mover"] = {"color": c, "size": z}
            where = {}
            for when, os_ in (("at", objs), ("was-at", prev_objs), ("home", first or [])):
                o = next((o for o in os_ if o["color"] == c and o["size"] == z), None)
                if o is not None:
                    where[when] = o
                    if when != "home":
                        res[when] = f"c{c}s{z}x{o['cx']}y{o['cy']}"
            m = next((m for m in res.get("moved", []) if (m["color"], m["size"]) == (c, z)), None)
            if m and "last-x" not in res and "lost" not in res and {"at", "home"} <= set(where):
                usual = steps.get((last.get("action"), c, z), {})
                if (where["at"]["cx"], where["at"]["cy"]) == (where["home"]["cx"], where["home"]["cy"]) and usual \
                        and (m["dx"], m["dy"]) != max(usual, key=usual.get):
                    res["reset"] = "yes"
            if m:
                along.update((o["color"], o["size"]) for o in res.get("moved", [])
                             if (o["dx"], o["dy"]) == (m["dx"], m["dy"]) and (o["color"], o["size"]) != (c, z))
            new_level = obs.get("levels_completed") != (prev_obs or {}).get("levels_completed")
            if "lost" in res or new_level:
                touched.clear(); given_up.clear(); stuck.clear(); goal = None
            elif event or "reset" in res:
                touched = set(recent)  # what it was touching made the change: that stays touched
                stuck.clear()
            usual = steps.get((last.get("action"), c, z), {})
            v = max(usual, key=usual.get) if usual else None
            if body and v and v != (0, 0) and not m and not new_level and "last-x" not in res \
                    and not ({"lost", "reset"} & set(res)):
                stuck.add((body[0], body[1], v))
            if "at" in where:
                me = where["at"]
                x0, y0, x1, y1 = me["x"] - 2, me["y"] - 2, me["x"] + me["w"] + 1, me["y"] + me["h"] + 1
                key = lambda o: (o["color"], o["size"], o["cx"], o["cy"])
                # touching: an object's point within the mover's box, or an object that vanished under it
                now = {key(o) for o in objs + prev_objs if x0 <= o["cx"] <= x1 and y0 <= o["cy"] <= y1}
                touched |= now
                recent = now | last_touch
                last_touch = now
                H, W = g.shape
                able = [o for o in objs if o["size"] <= GOAL_MAX and (o["color"], o["size"]) != (c, z)
                        and o["x"] > 0 and o["y"] > 0 and o["x"] + o["w"] < W and o["y"] + o["h"] < H
                        and (o["color"], o["size"]) not in along and key(o) not in given_up]
                cands = [o for o in able if key(o) not in touched]
                if not cands and touched - now:  # everything touched and nothing won: touching again may differ
                    touched = set(now)
                    cands = [o for o in able if key(o) not in touched]
                # the body: the mover and what moves along with it, next to it
                bx0, by0, bx1, by1 = me["x"], me["y"], me["x"] + me["w"] - 1, me["y"] + me["h"] - 1
                for o in objs:
                    if (o["color"], o["size"]) in along and o["x"] <= bx1 + 1 and o["x"] + o["w"] >= bx0 \
                            and o["y"] <= by1 + 1 and o["y"] + o["h"] >= by0:
                        bx0, by0 = min(bx0, o["x"]), min(by0, o["y"])
                        bx1, by1 = max(bx1, o["x"] + o["w"] - 1), max(by1, o["y"] + o["h"] - 1)
                body = (bx0, by0)
                if m and v and (m["dx"], m["dy"]) == v and "reset" not in res \
                        and "lost" not in res and not new_level and prev_grid is not None and prev_grid.shape == g.shape:
                    floor.update(np.unique(prev_grid[by0:by1 + 1, bx0:bx1 + 1]).tolist())
                plan = {}
                vecs = {max(d, key=d.get) for (a, cc, zz), d in steps.items() if (cc, zz) == (c, z) and d}
                vecs.discard((0, 0))
                keep = way_for == (goal, len(stuck)) and body in way and any(key(o) == goal for o in cands)
                if keep:  # on the way already planned: no need to plan again
                    plan = {goal: (way[body][1], way)}
                elif cands and floor and vecs:
                    free = np.isin(g, list(floor))
                    free[by0:by1 + 1, bx0:bx1 + 1] = True
                    for o in objs:
                        if o["size"] <= GOAL_MAX:
                            free[o["y"]:o["y"] + o["h"], o["x"]:o["x"] + o["w"]] = True
                    ox, oy = me["x"] - bx0, me["y"] - by0

                    def wanted(x, y):
                        mx0, my0 = x + ox - 2, y + oy - 2
                        mx1, my1 = x + ox + me["w"] + 1, y + oy + me["h"] + 1
                        return next((key(o) for o in cands if mx0 <= o["cx"] <= mx1 and my0 <= o["cy"] <= my1), None)
                    plan = route(g, free, (bx0, by0, bx1, by1), sorted(vecs), wanted, stuck)
                if cands:
                    # a goal it can find a way to, over colours its body has stood on, the nearest by that way;
                    # else the nearest as the crow flies. It keeps the goal while it lasts, so two goals at a like
                    # distance don't take turns.
                    pool = [o for o in cands if key(o) in plan] or cands
                    far = lambda o: plan[key(o)][0] if key(o) in plan else abs(o["cx"] - me["cx"]) + abs(o["cy"] - me["cy"])
                    t = next((o for o in pool if key(o) == goal), None) or min(pool, key=far)
                    dist = far(t)
                    if key(t) != goal:
                        goal, best, stale = key(t), dist, 0
                    elif dist < best:
                        best, stale = dist, 0
                    else:
                        stale += 1
                        if stale > GOAL_PATIENCE:
                            given_up.add(goal)
                    if key(t) in plan:
                        way, way_for = plan[key(t)][1], (goal, len(stuck))
                        vx, vy = way[body][0]
                        res["goal-dx"], res["goal-dy"] = (vx > 0) - (vx < 0), (vy > 0) - (vy < 0)
                    else:
                        res["goal-dx"] = (t["cx"] > me["cx"]) - (t["cx"] < me["cx"])
                        res["goal-dy"] = (t["cy"] > me["cy"]) - (t["cy"] < me["cy"])
        if first is None or "lost" in res or obs.get("attempt", attempt) != attempt:
            first = objs
        attempt = obs.get("attempt", attempt)
        prev_grid, prev_objs, prev_state, prev_obs = g, objs, state, obs
        print(json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
