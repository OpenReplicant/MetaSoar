"""E-18 preparation, no models: how much recurs in a WTQ stream. Writes results/wtq-recurrence.md.

The stream is the runner's: the ids of `problems_test1k.json` sorted, shuffled by `random.Random(17)` (`stream.stream_ids`),
the first 300 and the first 600. Questions are read through `stream.load_cases`, so no gold is used except the table
id, which is not a runner field. (Gold answers are not read at all.)

Operation classes are by ordered rules, as `RULES` in d1_intent.py: written from the questions of `problems_dev1k.json`
(a sample of WTQ's training split), then run on the stream's questions, which the rules were not written from.

Usage: python3 -I wtq_recurrence.py ../data/wtq-84dd647-problems [out.md]
"""
from __future__ import annotations

import json, os, random, re, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stream, stream_v2  # noqa: E402

PROMOTE_AFTER = 12  # E-17d: a handler is written from 3 labelled cases, then needs 9 of 9 agreements on later ones

MAX_WORDS = r"most|highest|largest|biggest|greatest|top|best|longest|oldest|latest|maximum|more than any"
MIN_WORDS = r"least|lowest|smallest|fewest|worst|shortest|youngest|earliest|minimum|less than any"
RULES = [  # (class, regex), first match wins; written from the dev sample's question sentences
    ("difference", r"difference|how many (more|fewer|less)\b|how much (more|less|longer|higher|lower)|\bapart\b|how many .* (more|fewer) than"),
    ("average", r"\baverage\b|\bmean\b"),
    ("sum", r"\btotal (amount|population|points|score|revenue|attendance|votes|time|money|number of (points|medals|goals|votes|runs|wins|seats|yards|people))\b|\bsum\b|\bcombined\b|\baltogether\b|\ball together\b"),
    ("count", r"how many|number of|\bcount\b|\btotal number\b|\bhow often\b|how many times"),
    ("comparison", r"\bor\b.*\?$|\bwhich (is|was|has|had|did)\b.*\b(higher|lower|larger|smaller|older|younger|more|less|greater|better|first|earlier|later)\b.*\bor\b|\bbefore or after\b|\bhigher or lower\b"),
    ("neighbour", r"\b(next|following|previous|preceding|prior to|immediately|succeeded|preceded|directly)\b|\bafter\b|\bbefore\b"),
    ("superlative", rf"\b({MAX_WORDS}|{MIN_WORDS})\b"),
    ("yes_no", r"^(did|does|do|is|was|were|are|has|have|had|can|could|will)\b|^(in|on|at|for) [\w ]{1,20}, (did|does|do|is|was|were|are|has|have|had)\b"),
    ("ordinal", r"\b(first|last|second|third|fourth|fifth|\d+(st|nd|rd|th))\b"),
    ("list", r"^(name|list|tell me|give me)\b|\b(other than|besides|except|aside from|apart from)\b|\bname (all|each|every|the)\b|\bwhich .* (are|were)\b|\bwho (are|were)\b"),
    ("lookup", r"^(what|who|when|where|which|in (what|which)|how (long|old|much|far|tall|high))\b"),
]


def operation(question):
    t = question.lower().strip()
    return next((name for name, rx in RULES if re.search(rx, t)), "other")


def fine(question, cls):
    """A second level under the operation class, by rule."""
    t = question.lower()
    if cls == "count":
        return "count:condition" if re.search(r"at least|more than|fewer than|less than|over|under|above|below|exactly|only|\bno\b|\bnot\b|\bbefore\b|\bafter\b|\bwith\b|\bfrom\b|\bin \d{4}", t) else "count:plain"
    if cls == "superlative":
        mx, mn = re.search(rf"\b({MAX_WORDS})\b", t), re.search(rf"\b({MIN_WORDS})\b", t)
        return "superlative:min" if mn and not mx else "superlative:max"
    if cls == "neighbour":
        return "neighbour:before" if re.search(r"before|previous|preceding|prior|preceded", t) else "neighbour:after"
    return cls


def online_recurrence(keys, ns=(300, 600)):
    """For the first n keys in order: distinct keys, keys seen >= 9 times, and the share of cases whose key was seen before."""
    out = {}
    for n in ns:
        c = Counter(keys[:n])
        seen, repeat = set(), 0
        for k in keys[:n]:
            repeat += k in seen
            seen.add(k)
        out[n] = {"distinct": len(c), "once": sum(v == 1 for v in c.values()), "ge9": sum(v >= 9 for v in c.values()),
                  "repeat": repeat / n, "ceiling": 0.0, "top": c.most_common(1)[0][1]}
    return out


def ceiling(keys, shapes, n, gate, after=PROMOTE_AFTER, lo=0):
    """The most cases a handler could answer: a case counts when its key already has `after` earlier cases and,
    with the shape gate, its shape was seen among the key's earlier cases. An upper bound: it assumes every
    handler is written and promoted on time, and is right."""
    seen, shp, hit = Counter(), defaultdict(set), 0
    for i, (k, s) in enumerate(zip(keys[:n], shapes[:n])):
        if i >= lo and seen[k] >= after and (not gate or s in shp[k]):
            hit += 1
        seen[k] += 1
        shp[k].add(s)
    return hit / (n - lo)


def coarse_shape(case):
    """Columns only by number and whether each is numeric-looking: a looser shape than stream_v2.shape."""
    cols = case["table_for_pd"]
    return f"{len(cols)}:" + "".join("N" if all(stream_v2.cell_kind(x) in ("num", "blank") for x in v) else "T" for v in cols.values())


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def main(data_dir, out_path):
    cases = stream.load_cases(data_dir, 600)
    probs = json.load(open(os.path.join(data_dir, "problems_test1k.json")))
    table_ids = [probs[c["id"]]["table_id"] for c in cases]  # the only non-runner field used
    shapes = [stream_v2.shape(c) for c in cases]
    cshapes = [coarse_shape(c) for c in cases]
    ops = [operation(c["question"]) for c in cases]
    fines = [fine(c["question"], o) for c, o in zip(cases, ops)]
    L = ["# WTQ recurrence: can E-18 test the ladder? (no models)", "",
         "Made by `wtq_recurrence.py` on `problems_test1k.json` (1,000 questions sampled with `random.Random(18)` from WTQ's",
         "`pristine-unseen-tables`; see `wtq.py`), read through `stream.load_cases` in the runner's fixed order (sorted ids,",
         "`random.Random(17)` shuffle). The first 300 and the first 600 questions are measured. Gold answers are not read.", ""]

    # tables
    tb = [len(c["table"]) for c in cases]
    rows = [len(next(iter(c["table_for_pd"].values()), [])) for c in cases]
    cols = [len(c["table_for_pd"]) for c in cases]
    med = lambda v: sorted(v)[len(v) // 2]
    q = lambda v, f: sorted(v)[int(f * (len(v) - 1))]
    L += ["## Table size (what the large model reads)", "",
          "| | median | 90th percentile | maximum |", "|---|---|---|---|",
          f"| rows | {med(rows)} | {q(rows, .9)} | {max(rows)} |", f"| columns | {med(cols)} | {q(cols, .9)} | {max(cols)} |",
          f"| characters of `table` | {med(tb)} | {q(tb, .9)} | {max(tb)} |", "",
          f"At about 4 characters a token, the median table is about {med(tb) // 4} tokens and the 90th percentile about {q(tb, .9) // 4}. "
          f"`stream.show` puts a table in as JSON, in each of 3 examples of a handler prompt, so handler prompts are several times longer than that.", ""]

    # shapes
    L += ["## Table shapes (`stream_v2.shape`)", "", "| First n cases | Same table as an earlier case | Distinct shapes | Shapes seen once | Shapes seen 9+ times | Cases whose shape was seen before | Largest shape |",
          "|---|---|---|---|---|---|---|"]
    tr = online_recurrence(table_ids)
    sr = online_recurrence(shapes)
    for n in (300, 600):
        L.append(f"| {n} | {pct(tr[n]['repeat'])} | {sr[n]['distinct']} | {sr[n]['once']} | {sr[n]['ge9']} | {pct(sr[n]['repeat'])} | {sr[n]['top']} cases |")
    cr = online_recurrence(cshapes)
    L += ["", "A looser shape (number of columns, and for each column whether every cell looks numeric or blank): "
          + "; ".join(f"first {n}: {cr[n]['distinct']} shapes, {cr[n]['ge9']} seen 9+ times, {pct(cr[n]['repeat'])} of cases repeat one" for n in (300, 600)) + ".", ""]

    # classes
    L += ["## Operation classes by rules", "", "Rules (`RULES` in `wtq_recurrence.py`, first match wins) were written from `problems_dev1k.json`, a sample of the training split, "
          "and then run on the stream.", "",
          "| Class | First 300 | Share | First 600 | Share | Example (from the stream) |", "|---|---|---|---|---|---|"]
    c3, c6 = Counter(ops[:300]), Counter(ops[:600])
    ex = {}
    for c, o in zip(cases, ops):
        ex.setdefault(o, c["question"])
    for o, v in c6.most_common():
        L.append(f"| {o} | {c3[o]} | {pct(c3[o] / 300)} | {v} | {pct(v / 600)} | {ex[o]} |")
    L.append("")
    orr = online_recurrence(ops)
    fr = online_recurrence(fines)
    L += ["## Recurrence of classes", "",
          f"A handler in E-17d is written from 3 labelled cases and promoted after 9 of 9 agreements on later ones, so a class needs about {PROMOTE_AFTER} cases before anything is cheap. "
          "\"Ceiling\" is the share of cases that arrive after their class has had 12 cases (counted from `lo`, the first case measured): an upper bound on handler coverage, which assumes every handler is written and promoted on time and is right. "
          "With the shape gate (E-17d's rule that a promoted handler answers only a shape it has agreed on), a case counts only if its table shape was already seen among that class's earlier cases.", "",
          "| Keys | First n | Distinct | Seen once | Seen 9+ times | Cases whose key was seen before | Ceiling, no shape gate | Ceiling, shape gate | Ceiling, loose-shape gate |",
          "|---|---|---|---|---|---|---|---|---|"]
    for name, keys in (("operation class", ops), ("fine class (second level)", fines)):
        r = online_recurrence(keys)
        for n in (300, 600):
            L.append(f"| {name} | {n} | {r[n]['distinct']} | {r[n]['once']} | {r[n]['ge9']} | {pct(r[n]['repeat'])} | {pct(ceiling(keys, shapes, n, False))} | "
                     f"{pct(ceiling(keys, shapes, n, True))} | {pct(ceiling(keys, cshapes, n, True))} |")
    L += ["", "At the 450 cases a run could use (E-18's draft, in chunks of 50): ceiling by operation class "
          f"{pct(ceiling(ops, shapes, 450, False))} with no shape gate, {pct(ceiling(ops, shapes, 450, True))} with the shape gate, "
          f"{pct(ceiling(ops, cshapes, 450, True))} with the loose-shape gate; by fine class {pct(ceiling(fines, shapes, 450, False))}, "
          f"{pct(ceiling(fines, shapes, 450, True))} and {pct(ceiling(fines, cshapes, 450, True))}."]
    L += ["", "Over the last 150 of 450 (cases 301 to 450, where E-17b and E-17d measured), the ceiling is "
          f"{pct(ceiling(ops, shapes, 450, False, lo=300))} / {pct(ceiling(ops, shapes, 450, True, lo=300))} / {pct(ceiling(ops, cshapes, 450, True, lo=300))} "
          "by operation class (no gate / exact-shape gate / loose-shape gate) and "
          f"{pct(ceiling(fines, shapes, 450, False, lo=300))} / {pct(ceiling(fines, shapes, 450, True, lo=300))} / {pct(ceiling(fines, cshapes, 450, True, lo=300))} by fine class."]
    L += ["", "Classes with 9 or more cases, by n:", ""]
    for n in (300, 600):
        c = Counter(ops[:n])
        L.append(f"- first {n}: " + ", ".join(f"{k} {v}" for k, v in c.most_common() if v >= 9))
    L += ["", "Fine classes with 9 or more cases:", ""]
    for n in (300, 600):
        c = Counter(fines[:n])
        L.append(f"- first {n}: " + ", ".join(f"{k} {v}" for k, v in c.most_common() if v >= 9))
    # the combination: how many classes x shape
    L += ["", "### Class and shape together", "",
          "A handler promoted for a (class, shape) pair would need that pair 9+ times:", ""]
    for n in (300, 600):
        c = Counter(zip(ops[:n], shapes[:n]))
        L.append(f"- first {n}: {len(c)} pairs, {sum(v >= 9 for v in c.values())} seen 9+ times, {sum(v == 1 for v in c.values())} seen once")
    L += ["", "## What the rules are and are not", "",
          "The classes are rough. They are regular expressions on the question, with no model and no table, so a class is a guess at the operation, "
          "not a measured intent. The `lookup` class is a catch-all for who/what/when/where questions with no other cue and holds many different operations "
          "(a column read, a row filter, a join of two cells); it is not one operation and no one handler would serve it. "
          "`count` mixes row counts with counts under a condition, and `sum` is rarer than its share of 'total' questions suggests, since "
          "\"total number of films\" is a row count. The check below is the author's reading of 30 questions, not a measurement of agreement: 27 look plausible and 3 are doubtful "
          "(\"by what number of votes did nixon lose to brown\" is a difference, labelled count; \"what is the total number of wins\" is a sum or a row count; "
          "\"each callsign in this list begins with...\" is not a question). The reading is of the sample as generated at the time of writing.", ""]
    rnd = random.Random(5)
    pick = rnd.sample(range(300), 30)
    L += ["| Question (random 30 of the first 300) | Class | Fine class |", "|---|---|---|"]
    for i in pick:
        L.append(f"| {cases[i]['question']} | {ops[i]} | {fines[i]} |")
    L += ["", "## Reading", "",
          "- Operation classes recur: by rules there are 12 classes, none seen once after 600 questions, and 9 or 10 of them seen 9 or more times. "
          "Recurrence of the class is not the limit.",
          "- Table shapes do not recur: the exact shape of E-17d's gate is new for about half the cases at 300 and a third at 600, and no (class, shape) pair "
          "reaches 9 cases in the first 300. With that gate, no run of 300 to 600 cases can have a handler answer much more than the ceilings above "
          "(the exact-shape rows), and E-17d's own falsifier (under 30% answered) would be met by the gate, whatever the handlers do.",
          "- The ceilings are upper bounds. They assume the handler is written and promoted on time and is right. Handler accuracy on WTQ is not measured here.",
          "- The rules cannot say which classes one handler could serve. `lookup`, `list`, `other` and `yes_no` together are about a fifth of the stream and are "
          "not one operation each.", ""]
    text = "\n".join(L) + "\n"
    with open(out_path, "w") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "results", "wtq-recurrence.md"))
