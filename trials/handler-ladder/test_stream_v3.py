"""Tests for E-18's runner (stream_v3.py) and report, with fake models: python3 -I -m unittest discover -s . -p 'test_*.py'

Fake WTQ-like data, 60 cases on tables of different schemas: `rows` (how many rows; the small model names it two ways,
so the class handler pools over two fine intents), `minus` (a count whose answer is one less: the class handler
disagrees there and is withdrawn), `most` (superlative; the template is right) and `name` (a lookup).
"""
import json, os, random, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import e18_report, stream, stream_v3  # noqa: E402

KINDS = (["rows"] * 24 + ["minus"] * 12 + ["most"] * 14 + ["name"] * 10)
COUNT_CODE = "def solve(table, question, choices):\n    return str(len(next(iter(table.values()))))"
QTEXT = {"rows": "How many rows are in the table", "minus": "How many rows minus one are listed",
         "most": "Which item has the most", "name": "What is the name in the first row"}


def build(root):
    rng = random.Random(0)
    probs = {}
    for i, kind in enumerate(rng.sample(KINDS, len(KINDS))):
        h1, h2 = rng.choice(["Team", "Player", "City", "Club"]), rng.choice(["Points", "Goals", "Votes", "Score"])
        rows = 3 + i % 4
        names = [f"N{i}x{j}" for j in range(rows)]
        vals = [str((i * 7 + j * 3) % 17 + j) for j in range(rows)]
        ans = {"rows": str(rows), "minus": str(rows - 1), "most": names[max(range(rows), key=lambda j: int(vals[j]))],
               "name": names[0]}[kind]
        q = f"{QTEXT[kind]} (case {i})?"
        probs[str(5000 + i)] = {"question": q, "choices": None, "table_title": None, "unit": None,
                                "table": "\n".join([f"{h1} | {h2}"] + [f"{a} | {b}" for a, b in zip(names, vals)]),
                                "table_for_pd": {h1: names, h2: vals}, "answer": [ans], "answer_type": "x", "table_id": f"t{i}"}
    d = os.path.join(root, "wtq")
    os.makedirs(d)
    with open(os.path.join(d, "problems_test1k.json"), "w") as f:
        json.dump(probs, f)
    return d, {p["question"]: p["answer"][0] for p in probs.values()}


def kind_of(text):
    return next(k for k, q in QTEXT.items() if q in text)


class Fakes:
    def __init__(self, lookup):
        self.lookup, self.n_rows = lookup, 0

    def large(self, text, max_tokens, prefill=None):
        if "Write a Python function" in text:
            return "```python\n" + COUNT_CODE + "\n```", {}
        q = next(q for q in self.lookup if q in text)
        return f"Work.\nAnswer: {self.lookup[q]}", {"completion_tokens": 5}

    def small(self, text, max_tokens):
        if "Intent: <key>" in text:
            k = kind_of(text.split("Question: ")[1])
            if k == "rows":
                self.n_rows += 1
                return f"Intent: {'count_rows' if self.n_rows % 2 else 'count_entries'}", {}
            return f"Intent: {k}_thing", {}
        if "Rewrite this worked solution" in text:
            return "1. Read the table.", {}
        q = next(q for q in self.lookup if q in text)
        return f"Answer: {self.lookup[q] if kind_of(q) == 'most' else 'zzz'}", {}


def fake_choose(question, options, instructions):
    p = {k: 0.0 for k in options} | {"none": 0.0}
    k = kind_of(question)
    if instructions == stream_v3.CLASS_INSTRUCTIONS:
        want = {"rows": "count", "minus": "count", "most": "superlative", "name": "lookup"}[k]
        p[f"c{list(stream_v3.CLASSES).index(want)}"] = 0.9
    else:  # fine: d1 says none for `rows` (so the small model's names, and merging, decide), matches the rest by kind
        hit = next((o for o, q in options.items() if kind_of(q) == k), None) if k != "rows" else None
        p[hit or "none"] = 0.9
    return p


def fake_embed(texts):
    return [[1.0 if kind_of(t) == k else 0.0 for k in QTEXT] for t in texts]


def run(tmp, d, lookup, out="out"):
    f = Fakes(lookup)
    s = stream_v3.StreamV3(d, os.path.join(tmp, out), f.large, f.small, chunk_size=20, n=60, log=lambda *_: None,
                           embed_fn=fake_embed, choose3_fn=fake_choose)
    for c in (1, 2, 3):
        s.run_chunk(c)
    return s, f


class T(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.d, self.lookup = build(self.tmp)

    def tearDown(self):
        self._t.cleanup()

    def test_agree_and_strict(self):
        self.assertTrue(stream_v3.agree("Spain, Italy", "Italy, Spain"))
        self.assertTrue(stream_v3.agree("12", "12.0"))
        self.assertFalse(stream_v3.agree("Spain", "Italy, Spain"))
        self.assertFalse(stream_v3.agree(None, "x"))
        c = {"choices": None}
        self.assertEqual(stream_v3.strict("1, 2, 3", c), "1, 2, 3")
        for bad in ("None", "<the answer only>", "x" * 400):
            self.assertIsNone(stream_v3.strict(bad, c))

    def test_end_to_end(self):
        s, f = run(self.tmp, self.d, self.lookup)
        recs = s.state["cases"]
        self.assertEqual({r["class"] for r in recs}, {"count", "superlative", "lookup"})
        self.assertTrue(all(r["intent"].split(":")[0] == r["class"] for r in recs))
        fine_count = {r["intent"] for r in recs if r["class"] == "count"}
        self.assertGreaterEqual(len(fine_count), 3, fine_count)  # count_rows, count_entries, minus_thing
        self.assertTrue(any(r["route"]["by"] == "merged" for r in recs))  # d1 said none, the small model named a known one
        self.assertEqual(len([k for k in s.state["intents"] if k.startswith("count:count_rows")]), 1)
        h = s.state["classes"]["count"]["handler"]
        self.assertEqual(h["scope"], "class")
        self.assertEqual(h["status"], "active")  # pooled over count_rows and count_entries
        self.assertGreaterEqual(stream_v3.stream_v2.wilson_lower(h["agree"], h["n"]), stream_v3.stream_v2.LOWER)
        used = {r["intent"] for r in recs if r["rung"] == "class_handler"}
        self.assertTrue({"count:count_rows", "count:count_entries"} <= used, used)
        self.assertTrue(s.state["intents"]["count:minus_thing"].get("withdrawn"))
        late_minus = [r for r in recs if r["intent"] == "count:minus_thing"][-3:]
        self.assertTrue(all(r["rung"] != "class_handler" for r in late_minus))
        for r in recs:
            if r["rung"] == "class_handler":
                self.assertIn(r["exact_admit"], (True, False))
                self.assertEqual(r["answer"], self.lookup[s.byid[r["id"]]["question"]])
        self.assertTrue(any(r["rung"] == "template" and r["class"] == "superlative" for r in recs))
        self.assertTrue(any(r["shadow_label"] for r in recs))

    def test_report(self):
        s, f = run(self.tmp, self.d, self.lookup)
        out = os.path.join(self.tmp, "out")
        self.assertGreater(e18_report.baseline(self.d, out, f.large, n=60, last=20, log=lambda *_: None), 0)
        text = e18_report.summary(out, self.d, chunk_size=20, last=20, total=60)
        for x in ("## E-18 verdict lines", "coverage below 30%", "paired difference", "| count |", "exact shape would have admitted"):
            self.assertIn(x, text)

    def test_no_gold(self):
        src = open(os.path.join(HERE, "stream_v3.py")).read()
        for banned in ("answer_canon", "answer_type", "table_id", "wtq.correct", "problems_test1k", 'get("answer")'):
            self.assertFalse(banned in src, banned)


if __name__ == "__main__":
    unittest.main()
