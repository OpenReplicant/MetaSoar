"""E-19's fixed operations on a table: a program (a small JSON object a model fills in) run with no model.

    {"op": OP, "column": C, "where": [{"column": C, "is": CMP, "value": V}, ...],
     "key": C, "items": [V, ...], "by": C, "n": 1, "than": V, "answer_as": FORM, "direction": DIR}

`table` maps column names to lists of string cells (as in handlers). Rows are kept when every `where` condition holds,
and, when `items` is given, when their `key` cell matches one of the items. A summary row (a label such as "Total")
is left out unless a condition names it. Then OP on those rows:

    count            how many rows
    sum, average     of `column`'s values
    max, min         `column`'s largest or smallest value
    argmax, argmin   `column`'s cell (the label column when absent) of the row(s) with the largest or smallest `by`
                     (`by` defaults to `column`, and then the answer is that largest or smallest cell itself)
    nth              `column`'s cell of the n-th row in table order (1 the first, -1 the last); with `by`, ranked by
                     `by`, largest first
    value            `column`'s cells of the rows (one value, or a list)
    next, previous   `column`'s cell of the row after or before the row that `items[0]` names in `key`
    difference       |`column`(items[0]) - `column`(items[1])|; with no items, max - min of `column`
    exists           "yes" if any row is kept, else "no"
    compare          `column` of items[0] against items[1] (or against `than`), in `direction` ("greater", "less" or
                     "equal"), answered `answer_as`: "yes_no", "item" (the item that is greater, or less), or a pair
                     of words: "more_less", "above_below", "higher_lower", "before_after", "longer_shorter",
                     "older_younger"
    consecutive      the longest run of adjacent rows (table order) that meet `where`

Values are read as numbers, then as dates (a year alone, "March 4, 2012", "2000-01" seasons), then as durations
("2:34.50", "2.04 seconds"). A comparison with a bare year (`> 2011`) compares the cell's year.

`run` raises `Unsupported` whenever the program does not fit the table: an unknown column, a `where` or item value
that no cell of its column matches, a value that does not parse, no rows left. The case then goes to the large model.
"""
from __future__ import annotations

import re

from handlers_lib import label_column, num

OPS = ("count", "sum", "average", "max", "min", "argmax", "argmin", "nth", "value", "next", "previous", "difference",
       "exists", "compare", "consecutive")
CMPS = ("=", "!=", ">", "<", ">=", "<=", "contains")
DIRECTIONS = ("greater", "less", "equal")
ANSWER_AS = ("yes_no", "item", "more_less", "above_below", "higher_lower", "before_after", "longer_shorter",
             "older_younger")
SUMMARY = {"total", "totals", "sum", "overall", "all", "grand total", "average", "mean"}
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                          "dec"))}


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
    if v is None:  # a leading number with text after it: "12 (3)", "1,234 people", "1.76 m"
        m = re.match(r"\s*[$£€]?(-?\d[\d,]*(?:\.\d+)?)(?![\d:/-])", str(cell))
        v = float(m.group(1).replace(",", "")) if m else None
    return v


YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")


def year_of(cell):
    m = YEAR.search(str(cell))
    return int(m.group(1)) if m else None


def date_value(cell):
    """A date as a sortable number (year, month, day), or None. A season "2000-01" or "2000–01" is its first year."""
    s = str(cell).lower()
    y = year_of(s)
    if y is None:
        return None
    mo = next((MONTHS[w[:3]] for w in re.findall(r"[a-z]+", s) if w[:3] in MONTHS and len(w) >= 3), 0)
    d = 0
    m = re.search(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?(?!\d)", YEAR.sub(" ", s))
    if mo and m:
        d = int(m.group(1))
    m = re.search(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", s)
    if m:
        mo, d = int(m.group(2)), int(m.group(3))
    return y * 10000 + mo * 100 + d


def duration(cell):
    """Seconds in "1:02:03", "2:34.50", "2.04 seconds", "3 min", or None."""
    s = str(cell).strip().lower()
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)\D{0,6}", s)
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.match(r"(\d+(?:\.\d+)?)\s*(s|sec|secs|seconds?|min|mins|minutes?|h|hrs?|hours?)\b", s)
    if m:
        return float(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)[0]]
    return None


def kind_of(cells):
    """How a column's cells are read: "duration", "date", or "number" (the commonest that parses)."""
    vals = [c for c in cells if str(c).strip()]
    if not vals:
        return "number"
    dur = sum(duration(c) is not None and ":" in str(c) for c in vals)
    months = sum(bool(re.search(r"[a-z]{3}", str(c).lower())) and date_value(c) is not None for c in vals)
    if dur >= len(vals) / 2:
        return "duration"
    if months >= len(vals) / 2:
        return "date"
    nums = sum(numeric(c) is not None for c in vals)
    if nums >= len(vals) / 2:
        return "number"
    if sum(date_value(c) is not None for c in vals) >= len(vals) / 2:
        return "date"
    if sum(duration(c) is not None for c in vals) >= len(vals) / 2:
        return "duration"
    return "number"


def value_of(cell, kind="number"):
    if kind == "duration":
        return duration(cell)
    if kind == "date":
        return date_value(cell)
    v = numeric(cell)
    return v if v is not None else duration(cell)


def cell_matches(cell, value, cmp="=", kind="number"):
    c, v = norm(cell), norm(value)
    if cmp == "contains":
        return v in c
    if cmp in ("=", "!="):
        a, b = numeric(cell), numeric(value)
        same = c == v or (a is not None and b is not None and a == b and re.fullmatch(r"[\d.,\s$%-]+", v) is not None)
        return same if cmp == "=" else not same
    if re.fullmatch(r"(1[0-9]{3}|20[0-9]{2})", v) and (kind == "date" or numeric(cell) is None):
        a, b = year_of(cell), int(v)  # "> 2011" on "March 2012" compares years
    else:
        a, b = value_of(cell, kind), value_of(value, kind)
    if a is None or b is None:
        return False
    return {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[cmp]


def rows_of(table):
    cols = list(table)
    n = len(table[cols[0]]) if cols else 0
    return [{c: table[c][i] for c in cols} for i in range(n)]


def is_summary(row, table):
    lab = label_column(table)
    return lab is not None and norm(row[lab]) in SUMMARY


def matches(table, rows, w):
    col, cmp, val = column(table, w.get("column", "")), w.get("is", "="), w.get("value", "")
    if cmp not in CMPS:
        raise Unsupported(f"comparison {cmp!r}")
    kind = kind_of(table[col])
    if cmp in ("=", "contains") and not any(cell_matches(r[col], val, cmp, kind) for r in rows_of(table)):
        raise Unsupported(f"no cell of {col!r} matches {val!r}")
    return [r for r in rows if cell_matches(r[col], val, cmp, kind)]


def select(table, prog):
    where = prog.get("where") or []
    rows = rows_of(table)
    names_summary = any(norm(w.get("value", "")) in SUMMARY for w in where)
    if not names_summary:
        rows = [r for r in rows if not is_summary(r, table)]
    for w in where:
        rows = matches(table, rows, w)
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


def scored(rows, col, table):
    kind = kind_of(table[col])
    out = [(value_of(r[col], kind), r) for r in rows]
    out = [(v, r) for v, r in out if v is not None]
    if not out:
        raise Unsupported(f"no values in {col!r}")
    return out, kind


WORDS = {"more_less": ("more", "less"), "above_below": ("above", "below"), "higher_lower": ("higher", "lower"),
         "before_after": ("after", "before"), "longer_shorter": ("longer", "shorter"), "older_younger": ("younger", "older")}


def compare(table, prog, out_col):
    """items[0] against items[1] or `than`. Dates: greater means later (so "before" when less)."""
    items = prog.get("items") or []
    if not items:
        raise Unsupported("compare needs an item")
    key = column(table, prog.get("key") or label_column(table))
    kind = kind_of(table[out_col])
    rows = select(table, {"items": items, "key": key})
    a = value_of(rows[0][out_col], kind)
    if len(items) >= 2:
        b = value_of(rows[1][out_col], kind)
    elif prog.get("than") not in (None, ""):
        than = str(prog["than"]).strip()
        if kind == "date" and re.fullmatch(r"\d{4}", than):
            a, b = (a // 10000 if a is not None else None), int(than)
        else:
            b = value_of(than, kind)
    else:
        raise Unsupported("compare needs two items or a value")
    if a is None or b is None:
        raise Unsupported("compare of values that do not parse")
    direction = prog.get("direction") or "greater"
    form = prog.get("answer_as") or "yes_no"
    if form == "yes_no":
        ok = {"greater": a > b, "less": a < b, "equal": a == b}.get(direction)
        if ok is None:
            raise Unsupported(f"direction {direction!r}")
        return "yes" if ok else "no"
    if a == b:
        return "same" if form != "item" else join([rows[0][key], rows[1][key]] if len(rows) > 1 else [rows[0][key]])
    if form == "item":
        if len(rows) < 2:
            raise Unsupported("item answer needs two items")
        first_wins = (a > b) if direction != "less" else (a < b)
        return join([rows[0 if first_wins else 1][key]])
    if form in WORDS:
        hi, lo = WORDS[form]
        return hi if a > b else lo
    raise Unsupported(f"answer_as {form!r}")


def run(table, prog):
    """-> the answer as a string (a list joined by ', '); raises Unsupported."""
    op = prog.get("op")
    if op not in OPS:
        raise Unsupported(f"op {op!r}")
    if not table or not rows_of(table):
        raise Unsupported("empty table")
    out_col = column(table, prog["column"]) if prog.get("column") else label_column(table)
    if op == "exists":
        return "yes" if select(table, prog) else "no"
    if op == "compare":
        return compare(table, prog, out_col)
    if op == "consecutive":
        rows = [r for r in rows_of(table) if not is_summary(r, table)]
        where = prog.get("where") or []
        for w in where:
            matches(table, rows, w)  # raises when a value matches no cell
        best = cur = 0
        for r in rows:
            cur = cur + 1 if all(matches(table, [r], w) for w in where) else 0
            best = max(best, cur)
        if best == 0:
            raise Unsupported("no rows")
        return str(best)
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
    if op in ("sum", "average"):
        vals = [v for v, _ in scored(rows, out_col, table)[0]]
        return fmt(sum(vals) if op == "sum" else sum(vals) / len(vals))
    if op in ("max", "min"):
        sc, _ = scored(rows, out_col, table)
        best = (max if op == "max" else min)(v for v, _ in sc)
        return join([r[out_col] for v, r in sc if v == best]) if kind_of(table[out_col]) != "number" else fmt(best)
    if op in ("argmax", "argmin"):
        by = column(table, prog.get("by") or prog.get("column") or "")
        sc, _ = scored(rows, by, table)
        best = (max if op == "argmax" else min)(v for v, _ in sc)
        col = out_col if prog.get("column") else label_column(table)
        return join([r[col] for v, r in sc if v == best])
    if op == "nth":
        n = int(prog.get("n") or 1)
        if prog.get("by"):
            by = column(table, prog["by"])
            sc, _ = scored(rows, by, table)
            rows = [r for v, r in sorted(sc, key=lambda x: -x[0])]
        if n == 0 or abs(n) > len(rows):
            raise Unsupported("no such position")
        return join([rows[n - 1 if n > 0 else n][out_col]])
    if op == "value":
        return join([r[out_col] for r in rows])
    if op == "difference":
        if prog.get("items"):
            if len(rows) != 2:
                raise Unsupported("difference needs two items")
            sc, _ = scored(rows, out_col, table)
            if len(sc) != 2:
                raise Unsupported("difference of values that do not parse")
            d = abs(sc[0][0] - sc[1][0])
            if kind_of(table[out_col]) == "date":
                d = abs(sc[0][0] // 10000 - sc[1][0] // 10000)  # in years
            return fmt(float(d))
        vals = [v for v, _ in scored(rows, out_col, table)[0]]
        d = max(vals) - min(vals)
        return fmt(float(d // 10000 if kind_of(table[out_col]) == "date" else d))
    raise Unsupported(op)
