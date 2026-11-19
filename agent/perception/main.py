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


def main():
    prev_grid, prev_objs, masked, prev_state, attempt = None, [], None, None, None
    moves = {}  # (colour, size) -> plain-action steps it moved on
    steps = {}  # (action, colour, size) -> {(dx, dy): count}
    first = None  # the objects of the attempt's first frame
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
            ry, rx = np.nonzero(rest)
            if 0 < len(ry) <= 2 and not masked[ry, rx].all():
                # a tick: leave out the region it belonged to, at its size before the tick, and say again what the
                # last frame was without it, so a step that only ticked reads as going nowhere
                for y, x in zip(ry.tolist(), rx.tolist()):
                    if not masked[y, x]:
                        y0, x0, y1, x1 = region_box(prev_grid, y, x)
                        masked[y0:y1 + 1, x0:x1 + 1] = True
                prev_state = signature(prev_grid, masked)
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
        if first is None or "lost" in res or obs.get("attempt", attempt) != attempt:
            first = objs
        attempt = obs.get("attempt", attempt)
        prev_grid, prev_objs, prev_state = g, objs, state
        print(json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
