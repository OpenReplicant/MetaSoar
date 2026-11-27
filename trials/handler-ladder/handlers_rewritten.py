"""Five extracted handlers rewritten on handlers_lib. Each keeps its intent's name and signature, so the tests can call
it next to the original code in results/state.json. Where a stem-and-leaf original was wrong, the comment says so.
"""
import re

from handlers_lib import (is_stem_leaf, label_column, match_choice, num, numeric_columns, row_by_label,
                          stem_leaf_values, threshold)


def find_minimum_count(table, question, choices):
    """The row (or stem-and-leaf value) with the fewest; with the most when the question asks for the most."""
    q = question.lower()
    least = any(w in q for w in ("fewest", "lowest", "minimum", "least", "smallest"))
    most = not least and any(w in q for w in ("most", "highest", "maximum", "largest"))
    if is_stem_leaf(table):
        vals = stem_leaf_values(table)
        ans = str(max(vals) if most else min(vals))
        if not choices and "members" in q:
            return ans + " members"
        return match_choice(ans, choices) or ans
    num_col = (numeric_columns(table) or [None])[0]
    if num_col is None:
        return None
    pairs = [(i, num(v)) for i, v in enumerate(table[num_col]) if num(v) is not None]
    if not pairs:
        return None
    idx = (max if most else min)(pairs, key=lambda p: p[1])[0]
    ans = table[label_column(table)][idx]
    return match_choice(ans, choices) or ans


def compute_max_count(table, question, choices):
    """The largest value of a stem-and-leaf table (stem 4, leaf 9 -> 49)."""
    if not is_stem_leaf(table):
        return None
    ans = str(max(stem_leaf_values(table)))
    return match_choice(ans, choices) or ans


def find_maximum_count(table, question, choices):
    """The row (or stem-and-leaf value) with the most; with the least when the question asks for it.
    Original bug: it took the stem-and-leaf path only when the question said "stem" or "leaf", so a question such as
    "What is the largest number of roses?" on a stem-and-leaf table returned a stem's leaf text. Here the table decides."""
    q = question.lower()
    if is_stem_leaf(table):
        vals = stem_leaf_values(table)
        ans = str(max(vals) if any(w in q for w in ("largest", "most", "max")) else min(vals))
        return match_choice(ans, choices) or ans
    num_col = (numeric_columns(table) or [None])[0]
    if num_col is None:
        return None
    label = next(c for c in table if c != num_col)
    pairs = [(lab, num(v)) for lab, v in zip(table[label], table[num_col]) if num(v) is not None]
    if not pairs:
        return None
    if any(w in q for w in ("largest", "most", "max", "highest")):
        best = max(pairs, key=lambda p: p[1])
    elif any(w in q for w in ("smallest", "least", "min", "lowest")):
        best = min(pairs, key=lambda p: p[1])
    else:
        best = max(pairs, key=lambda p: p[1])
    return match_choice(best[0], choices) or best[0]


def count_people_interviewed_no(table, question, choices):
    """How many people meet the threshold in the question, from a value-and-frequency table or a stem-and-leaf table.
    Original bug: stem-and-leaf values were read as stem + leaf/10 (stem 4, leaf 2 -> 4.2), so "at least 40" counted
    nothing. Here stem 4, leaf 2 is 42."""
    cols = list(table)
    freq_col = next((c for c in cols if "freq" in c.lower()), None)
    if is_stem_leaf(table):
        vals = stem_leaf_values(table)
        freqs = [1] * len(vals)
    else:
        val_col = next((c for c in cols if c != freq_col), None)
        if val_col is None:
            return None
        vals = [num(v) for v in table[val_col]]
        freqs = [num(f) or 0 for f in table[freq_col]] if freq_col else [1] * len(vals)
    test = threshold(question)
    total = sum(f for v, f in zip(vals, freqs) if v is not None and (test is None or test(v)))
    ans = int(total) if total == int(total) else total
    return match_choice(str(ans), choices) or str(ans)


def compute_total_cost(table, question, choices):
    """Total price of the items the question asks to buy ("buy 2 pencils and a ruler"), from an item-and-price table.
    The count after "buy" applies to every item, as in the original."""
    m = re.search(r"buy (?:(\d+) )?(.+?)(?:\?|$)", question.lower())
    if not m:
        return None
    qty = int(m.group(1)) if m.group(1) else 1
    label = label_column(table)
    price_col = next((c for c in table if c != label), label)
    total = 0.0
    for part in re.split(r",| and ", m.group(2)):
        part = re.sub(r"^(a|an|the)\s+", "", part.strip())
        i = row_by_label(table, part)
        if i is not None and num(table[price_col][i]) is not None:
            total += num(table[price_col][i]) * qty
    ans = f"${total:,.2f}"
    return match_choice(ans, choices) or ans
