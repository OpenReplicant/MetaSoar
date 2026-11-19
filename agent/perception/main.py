"""The agent's perception (M-09): raw observations in, symbols out, one JSON line each way per step.

What it reports knows no particular game:
- for a grid of colours (an observation key holding a 2-D array larger than the adapter puts on the input link raw):
  `objects`, the connected regions of one colour (4-neighbour), except the grid's most common colour (the
  background), largest first, at most MAX_OBJECTS: id, color, size, x, y (top-left), w, h, cx, cy (centre, rounded)
- `changed`: how many cells differ from the last frame, and their bounding box
- `moved`: objects that kept their colour and size but shifted since the last frame (dx, dy)
- `effect`: what the action just taken did: `moved` (something moved), `changed` (more than two cells), else `none`
  (a change of one or two cells, like a move counter ticking, is no effect)
- `last-action`, and `last-x`, `last-y` for a point: what was just done
- `background`: that commonest colour
Standard library only; it keeps the last frame between steps, nothing else.
"""
import json
import sys
from collections import Counter

MAX_OBJECTS = 24


def grid_of(obs):
    for v in (obs or {}).values():
        if isinstance(v, list) and len(v) > 8 and isinstance(v[0], list) and len(v) * len(v[0]) > 1024:
            return v
    return None


def objects(g):
    h, w = len(g), len(g[0])
    bg = Counter(c for row in g for c in row).most_common(1)[0][0]
    seen = [[False] * w for _ in range(h)]
    out = []
    for y in range(h):
        for x in range(w):
            if seen[y][x] or g[y][x] == bg:
                continue
            col, stack, cells = g[y][x], [(y, x)], []
            seen[y][x] = True
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < h and 0 <= nx < w and not seen[ny][nx] and g[ny][nx] == col:
                        seen[ny][nx] = True
                        stack.append((ny, nx))
            ys, xs = [c[0] for c in cells], [c[1] for c in cells]
            out.append({"color": col, "size": len(cells), "x": min(xs), "y": min(ys), "w": max(xs) - min(xs) + 1,
                        "h": max(ys) - min(ys) + 1, "cx": round(sum(xs) / len(xs)), "cy": round(sum(ys) / len(ys))})
    out.sort(key=lambda o: -o["size"])
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


def main():
    prev_grid, prev_objs = None, []
    for line in sys.stdin:
        msg = json.loads(line)
        g = grid_of(msg.get("observation"))
        if g is None:
            print(json.dumps({}), flush=True)
            continue
        bg, objs = objects(g)
        res = {"background": bg, "count": len(objs), "objects": objs[:MAX_OBJECTS]}
        if prev_grid is not None:
            diff = [(y, x) for y in range(len(g)) for x in range(len(g[0])) if g[y][x] != prev_grid[y][x]]
            res["changed"] = {"cells": len(diff)}
            if diff:
                ys, xs = [d[0] for d in diff], [d[1] for d in diff]
                res["changed"].update({"x": min(xs), "y": min(ys), "w": max(xs) - min(xs) + 1, "h": max(ys) - min(ys) + 1})
            moved = moved_objects(objs[:MAX_OBJECTS], prev_objs)
            res["moved"] = moved[:8]
            # a change of one or two cells and nothing moved (a move counter ticking) counts as no effect
            res["effect"] = "moved" if moved else ("changed" if len(diff) > 2 else "none")
        last = msg.get("last") or {}
        if last.get("action"):
            res["last-action"] = last["action"]
            params = last.get("params") or {}
            if "x" in params and "y" in params:
                res["last-x"], res["last-y"] = int(params["x"]), int(params["y"])
        prev_grid, prev_objs = g, objs
        print(json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
