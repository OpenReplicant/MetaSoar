"""Shared helpers for handlers: solve(table, question, choices), where table maps column names to lists of string cells.

Standard library only. Each function is short and works on the table's names and cells, not on the question,
except where a function takes the question as an argument.
"""
import re

__all__ = ["num", "numeric_columns", "label_column", "is_stem_leaf", "stem_leaf_values", "parse_time",
           "match_choice", "row_by_label", "threshold"]


def num(cell):
    """The number in a cell as a float, or None. Strips $, commas, % and unit words ("5 cars" -> 5.0).
    Accepts fractions ("1/2" -> 0.5, "2 1/2" -> 2.5, "-1/4" -> -0.25). Clock times and text give None."""
    s = str(cell)
    if ":" in s or re.search(r"\d\s*[AaPp]\.?[Mm]\.?(\s|$)", s):
        return None
    s = re.sub(r"[$,%]", "", s)
    s = re.sub(r"[A-Za-z]+\.?", " ", s).strip()
    m = re.fullmatch(r"(-)?(?:(\d+)\s+)?(\d+)\s*/\s*(\d+)", s)
    if m:
        if int(m.group(4)) == 0:
            return None
        v = int(m.group(2) or 0) + int(m.group(3)) / int(m.group(4))
        return -v if m.group(1) else v
    if re.fullmatch(r"-?\d*\.?\d+", s):
        return float(s)
    return None


def numeric_columns(table):
    """Names of the columns whose non-empty cells all parse with num(), in table order."""
    out = []
    for col, cells in table.items():
        vals = [c for c in cells if str(c).strip()]
        if vals and all(num(c) is not None for c in vals):
            out.append(col)
    return out


def label_column(table):
    """The first column that is not numeric (it holds the row labels). Falls back to the first column; None if empty."""
    cols = list(table)
    if not cols:
        return None
    numeric = set(numeric_columns(table))
    return next((c for c in cols if c not in numeric), cols[0])


def is_stem_leaf(table):
    """True for a stem-and-leaf table: two columns named Stem and Leaf (case and spaces ignored, so "Leaf " counts),
    whole-number stems, and leaves that are comma-separated whole numbers. Decided from names and cells only."""
    if len(table) != 2:
        return False
    names = {str(c).strip().lower(): c for c in table}
    if set(names) != {"stem", "leaf"}:
        return False
    stems, leaves = table[names["stem"]], table[names["leaf"]]
    if not stems or len(stems) != len(leaves):
        return False
    return (all(re.fullmatch(r"\s*\d+\s*", str(s)) for s in stems)
            and all(re.fullmatch(r"\s*\d+(\s*,\s*\d+)*\s*", str(l)) for l in leaves))


def stem_leaf_values(table):
    """Every value of a stem-and-leaf table as a whole number, stem then leaf (stem 2, leaf 1 -> 21), in table order.
    Returns [] when is_stem_leaf(table) is False."""
    if not is_stem_leaf(table):
        return []
    names = {str(c).strip().lower(): c for c in table}
    out = []
    for s, l in zip(table[names["stem"]], table[names["leaf"]]):
        for leaf in str(l).split(","):
            out.append(int(s) * 10 + int(leaf))
    return out


def parse_time(s):
    """Minutes after midnight for a clock time, or None. "11:15 A.M." -> 675, "2.10 P.M." -> 850,
    "12:30 A.M." -> 30, "12:00 P.M." -> 720. Without A.M. or P.M. the hour is read as given ("14:05" -> 845)."""
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*(?:([AaPp])\.?\s*[Mm]\.?)?\s*", str(s))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    ap = (m.group(3) or "").lower()
    if mi > 59 or h > 23 or (ap and not 1 <= h <= 12):
        return None
    if ap == "p" and h != 12:
        h += 12
    if ap == "a" and h == 12:
        h = 0
    return h * 60 + mi


def match_choice(answer, choices):
    """The entry of choices that equals answer, as written, or None. Text matches ignoring case, spaces, $ and commas;
    failing that, numbers match by value ("$3.50" equals 3.5). None entries are skipped."""
    if not choices:
        return None
    key = re.sub(r"[\s$,]", "", str(answer)).lower()
    for ch in choices:
        if ch is not None and re.sub(r"[\s$,]", "", str(ch)).lower() == key:
            return ch
    a = num(answer)
    if a is not None:
        for ch in choices:
            if ch is not None and num(ch) is not None and abs(num(ch) - a) < 1e-9:
                return ch
    return None


def _forms(word):
    """A label with its plural and singular forms: "pencil" -> pencil, pencils; "bunch" -> bunch, bunches."""
    out = [word, word + "s", word + "es"]
    if word.endswith("y"):
        out.append(word[:-1] + "ies")
    if word.endswith("ies"):
        out.append(word[:-3] + "y")
    if word.endswith("es"):
        out.append(word[:-2])
    if word.endswith("s"):
        out.append(word[:-1])
    return out


def row_by_label(table, text):
    """Index of the row whose label (label_column) appears in text, case-insensitively, as whole words, in plural or
    singular form. The longest matching label wins, so "green apple" beats "apple". None if no label appears."""
    col = label_column(table)
    if col is None:
        return None
    t = str(text).lower()
    best = None
    for i, lab in enumerate(table[col]):
        word = str(lab).strip().lower()
        if word and any(re.search(r"(?<![a-z])" + re.escape(f) + r"(?![a-z])", t) for f in _forms(word)):
            if best is None or len(word) > best[0]:
                best = (len(word), i)
    return None if best is None else best[1]


def threshold(question):
    """A test (a function from a number to bool) for the comparison in question, or None if there is none.
    "at least" / "no fewer than" -> >=; "at most" / "no more than" -> <=; "more than" / "greater than" / "over" /
    "above" -> >; "less than" / "fewer than" / "under" / "below" -> <. An "or equal to" after the word makes it
    inclusive."""
    m = re.search(r"(at least|no fewer than|at most|no more than|more than|greater than|over|above|less than|"
                  r"fewer than|under|below)(\s+or equal to)?\s+(-?\d+(?:\.\d+)?)", question.lower())
    if not m:
        return None
    word, inclusive, x = m.group(1), bool(m.group(2)), float(m.group(3))
    if word in ("at least", "no fewer than") or (inclusive and word in ("more than", "greater than", "over", "above")):
        return lambda v: v >= x
    if word in ("at most", "no more than") or (inclusive and word in ("less than", "fewer than", "under", "below")):
        return lambda v: v <= x
    if word in ("more than", "greater than", "over", "above"):
        return lambda v: v > x
    return lambda v: v < x
