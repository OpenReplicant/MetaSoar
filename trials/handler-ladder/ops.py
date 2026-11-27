"""E-19's fixed operations on a table: a program (a small JSON object a small model fills in) run with no model.

    {"op": OP, "column": C, "where": [{"column": C, "is": CMP, "value": V}, ...],
     "key": C, "items": [V, ...], "by": C, "n": 1}

`table` maps column names to lists of string cells (as in handlers). Rows are kept when every `where` condition holds,
and, when `items` is given, when their `key` cell matches one of the items. Then OP on those rows:

    count            how many rows
    sum, average     of `column`'s numbers
    max, min         `column`'s largest or smallest number
    argmax, argmin   `column`'s cell (the label column when absent) of the row(s) with the largest or smallest `by`
    nth              `column`'s cell of the n-th row in table order (1 the first, -1 the last); with `by`, ranked by
                     `by`, largest first
    value            `column`'s cells of the rows (one value, or a list)
    next, previous   `column`'s cell of the row after or before the row that `items[0]` names in `key`
    difference       |`column`(items[0]) - `column`(items[1])|; with no items, max - min of `column`
    exists           "yes" if any row is kept, else "no"

`run` raises `Unsupported` whenever the program does not fit the table: an unknown column, a `where` or item value
that no cell of its column matches, a number that does not parse, no rows left. The case then goes to the large model.
"""
from __future__ import annotations

import re

from handlers_lib import label_column, num

OPS = ("count", "sum", "average", "max", "min", "argmax", "argmin", "nth", "value", "next", "previous", "difference",
       "exists")
CMPS = ("=", "!=", ">", "<", ">=", "<=", "contains")


class Unsupported(ValueError):
    pass


def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip().lower().strip(" .\"'")


def column(table, name):
    if name in table:
        return name
    hits = [c for c in table if norm(c) == norm(name)]
    if len(hits) == 1:
        return hits[0]
    raise Unsupported(f"no column {name!r}")


def numeric(cell):
    v = num(cell)
    if v is None:  # a leading number with text after it: "12 (3)", "1,234 people", "1998-99"
        m = re.match(r"\s*\$?(-?\d[\d,]*(?:\.\d+)?)", str(cell))
        v = float(m.group(1).replace(",", "")) if m else None
    return v


def cell_matches(cell, value, cmp="="):
    c, v = norm(cell), norm(value)
    if cmp == "contains":
        return v in c
    a, b = numeric(cell), numeric(value)
    if cmp in ("=", "!="):
        same = c == v or (a is not None and b is not None and a == b and re.fullmatch(r"[\d.,\s$%-]+", v) is not None)
        return same if cmp == "=" else not same
    if a is None or b is None:
        return False
    return {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[cmp]


def rows_of(table):
    cols = list(table)
    n = len(table[cols[0]]) if cols else 0
    return [{c: table[c][i] for c in cols} for i in range(n)]


def select(table, prog):
    rows = rows_of(table)
    for w in prog.get("where") or []:
        col, cmp, val = column(table, w.get("column", "")), w.get("is", "="), w.get("value", "")
        if cmp not in CMPS:
            raise Unsupported(f"comparison {cmp!r}")
        if cmp in ("=", "contains") and not any(cell_matches(r[col], val, cmp) for r in rows_of(table)):
            raise Unsupported(f"no cell of {col!r} matches {val!r}")
        rows = [r for r in rows if cell_matches(r[col], val, cmp)]
    items = prog.get("items") or []
    if items:
        key = column(table, prog.get("key") or label_column(table))
        picked = []
        for it in items:
            hit = [r for r in rows if cell_matches(r[key], it)] or [r for r in rows if cell_matches(r[key], it, "contains")]
            if not hit:
                raise Unsupported(f"no row named {it!r} in {key!r}")
            picked.append(hit[0])
        rows = picked
    return rows


def fmt(v):
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else f"{v:.4g}" if abs(v) < 1e6 else str(round(v, 2))
    return str(v).strip()


def join(cells):
    out = []
    for c in cells:
        c = str(c).strip()
        if c and c not in out:
            out.append(c)
    if not out:
        raise Unsupported("no answer")
    return ", ".join(out)


def numbers(rows, col):
    vals = [numeric(r[col]) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        raise Unsupported(f"no numbers in {col!r}")
    return vals


def run(table, prog):
    """-> the answer as a string (a list joined by ', '); raises Unsupported."""
    op = prog.get("op")
    if op not in OPS:
        raise Unsupported(f"op {op!r}")
    if not table or not rows_of(table):
        raise Unsupported("empty table")
    out_col = column(table, prog["column"]) if prog.get("column") else label_column(table)
    if op == "exists":
        try:
            return "yes" if select(table, prog) else "no"
        except Unsupported:
            raise
    if op in ("next", "previous"):
        items = prog.get("items") or []
        if not items:
            raise Unsupported("no anchor")
        key = column(table, prog.get("key") or label_column(table))
        rows = rows_of(table)
        idx = [i for i, r in enumerate(rows) if cell_matches(r[key], items[0])]
        if not idx:
            raise Unsupported(f"no row named {items[0]!r}")
        j = idx[0] + (1 if op == "next" else -1)
        if not 0 <= j < len(rows):
            raise Unsupported("no row there")
        return join([rows[j][out_col]])
    rows = select(table, prog)
    if op == "count":
        return str(len(rows))
    if not rows:
        raise Unsupported("no rows")
    if op == "sum":
        return fmt(sum(numbers(rows, out_col)))
    if op == "average":
        v = numbers(rows, out_col)
        return fmt(sum(v) / len(v))
    if op in ("max", "min"):
        v = numbers(rows, out_col)
        return fmt(max(v) if op == "max" else min(v))
    if op in ("argmax", "argmin"):
        by = column(table, prog.get("by") or prog.get("column") or "")
        scored = [(numeric(r[by]), r) for r in rows if numeric(r[by]) is not None]
        if not scored:
            raise Unsupported(f"no numbers in {by!r}")
        best = (max if op == "argmax" else min)(s for s, _ in scored)
        col = out_col if prog.get("column") and prog.get("column") != prog.get("by") else label_column(table)
        return join([r[col] for s, r in scored if s == best])
    if op == "nth":
        n = int(prog.get("n") or 1)
        if prog.get("by"):
            by = column(table, prog["by"])
            rows = sorted([r for r in rows if numeric(r[by]) is not None], key=lambda r: -numeric(r[by]))
        if n == 0 or abs(n) > len(rows):
            raise Unsupported("no such position")
        return join([rows[n - 1 if n > 0 else n][out_col]])
    if op == "value":
        return join([r[out_col] for r in rows])
    if op == "difference":
        if prog.get("items"):
            if len(rows) != 2:
                raise Unsupported("difference needs two items")
            a, b = (numeric(r[out_col]) for r in rows)
            if a is None or b is None:
                raise Unsupported("difference of non-numbers")
            return fmt(abs(a - b))
        v = numbers(rows, out_col)
        return fmt(max(v) - min(v))
    raise Unsupported(op)
