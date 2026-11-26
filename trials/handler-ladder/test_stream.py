"""Tests for the E-17 stream runner with fake models (no server, no GPU): python3 -I -m unittest

Fake data, 40 cases of three intents: `total` (sum a column; a handler promotes; one late case has an "n/a" cell so
the promoted handler raises), `most` (choices; the small model's template is right, so it promotes), `difference`
(its handler always raises, never promotes). The fake large model answers from a lookup and writes handlers by regex.
"""
import json, os, re, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import baseline, stream, summarize  # noqa: E402

CODE = {"total": "def solve(table, question, choices):\n    return str(sum(int(x) for x in table['count']))",
        "most": "def solve(table, question, choices):\n    j = max(range(len(table['count'])), key=lambda i: int(table['count'][i]))\n    return table['item'][j].lower()",
        "difference": "def solve(table, question, choices):\n    raise ValueError('no')"}
KINDS = ["total"] * 18 + ["most"] * 12 + ["difference"] * 10
QTEXT = {"total": "How many items in total?", "most": "Which item has the most?", "difference": "What is the difference?"}


def kind_of(text):
    return next(k for k, w in (("total", "total"), ("most", "most"), ("difference", "difference")) if w in text)


def build(root, gold_tag=""):
    """Write fake problems_test1k.json; return (data_dir, lookup question -> answer). n/a goes in the stream's last `total`."""
    probs = {}
    for i, kind in enumerate(KINDS):
        counts, items = [str(3 + (i * 7) % 11 + j) for j in range(3)], ["Apple", "Pear", "Plum"]
        q = f"{QTEXT[kind]} (case {i})"
        ans = {"total": str(sum(map(int, counts))), "most": items[2], "difference": str(int(counts[2]) - int(counts[0]))}[kind]
        probs[f"{1000 + i}"] = {"question": q, "choices": items if kind == "most" else None, "answer": ans + gold_tag,
                                "unit": None, "table_title": "T", "ans_type": "integer_number" if kind != "most" else "other",
                                "table": "\n".join(f"{a} | {b}" for a, b in zip(items, counts)),
                                "table_for_pd": {"item": items, "count": counts}, "solution": "SECRET"}
    order = stream.stream_ids(list(probs), len(probs))
    na = [p for p in order if "total" in probs[p]["question"]][-1]
    probs[na]["table_for_pd"]["count"][1] = "n/a"
    probs[na]["answer"] = str(int(probs[na]["table_for_pd"]["count"][0]) + int(probs[na]["table_for_pd"]["count"][2])) + gold_tag
    d = os.path.join(root, "data" + gold_tag)
    os.makedirs(d)
    with open(os.path.join(d, "problems_test1k.json"), "w") as f:
        json.dump(probs, f)
    return d, {p["question"]: p["answer"].removesuffix(gold_tag) if gold_tag else p["answer"] for p in probs.values()}, na


class Fakes:
    def __init__(self, lookup, crash_after=None):
        self.lookup, self.crash_after, self.n = lookup, crash_after, 0

    def find(self, text):
        return next(q for q in self.lookup if q in text)

    def large(self, text, max_tokens, prefill=None):
        self.n += 1
        if self.crash_after and self.n > self.crash_after:
            raise RuntimeError("crash")
        if "Write a Python function" in text:
            return "```python\n" + CODE[kind_of(text)] + "\n```", {"completion_tokens": 50}
        return f"Work.\nAnswer: {self.lookup[self.find(text)]}", {"prompt_tokens": 10, "completion_tokens": 20}

    def small(self, text, max_tokens):
        if "Intent: <key>" in text:
            q = text.split("Question: ")[1]
            return f"Thinking...\nIntent: {'Total_Items!' if 'total' in q else 'most item' if 'most' in q else 'difference'}", {}
        if "Rewrite this worked solution" in text:
            return "1. Read the column.\n2. Combine it.", {}
        ans = self.lookup[self.find(text)]
        return f"Answer: {ans.lower() if not ans.isdigit() else '0'}", {}  # right for choices (lowercase), wrong for numbers


def new_stream(tmp, d, fakes, out="out", chunk=10):
    return stream.Stream(d, os.path.join(tmp, out), fakes.large, fakes.small, chunk_size=chunk, n=40, log=lambda *_: None)


def run_all(tmp, d, lookup, out="out"):
    s = new_stream(tmp, d, Fakes(lookup), out)
    for c in (1, 2, 3, 4):
        s.run_chunk(c)
    return s


class T(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.d, self.lookup, self.na = build(self.tmp)

    def tearDown(self):
        self._t.cleanup()

    def test_end_to_end(self):
        s = run_all(self.tmp, self.d, self.lookup)
        with open(os.path.join(self.tmp, "out", "stream.jsonl")) as f:
            recs = [json.loads(line) for line in f]
        self.assertEqual([r["id"] for r in recs], [c["id"] for c in s.cases])
        self.assertEqual({r["intent"] for r in recs}, {"total_items", "most_item", "difference"})
        cands = {k: v["candidates"] for k, v in s.state["intents"].items()}
        self.assertEqual(cands["total_items"]["handler"]["status"], "active")  # handler promotion
        self.assertEqual(cands["most_item"]["template"]["status"], "active")  # template promotion
        # no starvation: while the template answers, the large model labels for the shadowed handler, which promotes
        self.assertEqual(cands["most_item"]["handler"]["status"], "active")
        self.assertTrue(any(r["shadow_label"] for r in recs if r["intent"] == "most_item"))
        self.assertEqual([r for r in recs if r["intent"] == "most_item"][-1]["rung"], "handler")  # the cheaper rung wins
        dh = cands["difference"]["handler"]  # never agrees: rewritten once (v2), never promoted
        self.assertEqual((dh["version"], dh["agree"]), (2, 0))
        self.assertNotEqual(dh["status"], "active")
        self.assertEqual(cands["total_items"]["template"]["status"], "discarded")  # small model is wrong on numbers
        self.assertTrue(any(r["rung"] == "handler" for r in recs) and any(r["rung"] == "template" for r in recs))
        fb = [r for r in recs if r["fallback"]]  # the n/a case: the promoted handler raises, the large model answers
        self.assertEqual([r["id"] for r in fb], [self.na])
        self.assertEqual((fb[0]["rung"], fb[0]["fallback_from"]), ("large", "handler"))
        self.assertEqual(fb[0]["answer"], self.lookup[s.byid[self.na]["question"]])
        for r in recs:  # choice mapping: template answers "apple" are mapped onto the choice "Apple"
            if r["intent"] == "most_item":
                self.assertEqual(r["answer"], "Apple" if r["answer"].lower() == "apple" else r["answer"])
                self.assertIn(r["answer"], ["Apple", "Pear", "Plum"])
        first = next(r for r in recs if r["rung"] == "handler")
        self.assertEqual(first["large"]["calls"], 0)
        self.assertEqual(first["policies"]["handler"], 1)
        self.assertEqual(sum(r["large"]["calls"] for r in recs), s.large.calls)
        self.assertGreater(s.small.calls, 40)

    def test_chunks_in_order(self):
        s = new_stream(self.tmp, self.d, Fakes(self.lookup))
        with self.assertRaises(stream.ChunkError):
            s.run_chunk(2)
        s.run_chunk(1)
        self.assertEqual(len(s.done), 10)
        self.assertEqual(s.run_chunk(1), 0)  # idempotent

    def test_resume_matches_straight_run(self):
        straight = run_all(self.tmp, self.d, self.lookup, "straight")
        with self.assertRaises(RuntimeError):
            new_stream(self.tmp, self.d, Fakes(self.lookup, crash_after=5), "crash").run_chunk(1)
        mid = new_stream(self.tmp, self.d, Fakes(self.lookup), "crash")
        self.assertTrue(0 < len(mid.done) < 10)
        for c in (1, 2, 3, 4):
            mid.run_chunk(c)
        key = lambda s: [(r["id"], r["intent"], r["rung"], r["answer"], r["fallback"]) for r in s.state["cases"]]
        self.assertEqual(key(mid), key(straight))
        self.assertEqual(len({r["id"] for r in mid.state["cases"]}), 40)
        self.assertEqual(mid.state["intents"].keys(), straight.state["intents"].keys())

    def test_no_gold_in_runner(self):
        cases = stream.load_cases(self.d, 40)
        for c in cases:
            self.assertEqual(set(c), {"id", *stream.PROBLEM_FIELDS})
        with open(os.path.join(HERE, "stream.py")) as f:
            src = f.read()
        for banned in ("ans_type", "ques_type", "smoke.correct", '"solution"', 'get("answer")'):
            self.assertFalse(banned in src, banned)
        d2, lookup2, _ = build(self.tmp, gold_tag="-WRONG")  # different gold, same problems: same run
        a = run_all(self.tmp, self.d, self.lookup, "a")
        b = run_all(self.tmp, d2, lookup2, "b")
        key = lambda s: [(r["id"], r["intent"], r["rung"], r["answer"]) for r in s.state["cases"]]
        self.assertEqual(key(a), key(b))

    def test_check_and_agreement(self):
        case = {"choices": ["Apple", "$1,200.00", "Yes"]}
        self.assertEqual(stream.check(" apple. ", case), "Apple")
        self.assertEqual(stream.check("1200", case), "Apple" and "$1,200.00")
        self.assertEqual(stream.check("YES", case), "Yes")
        self.assertIsNone(stream.check("banana", case))
        self.assertIsNone(stream.check("  ", {"choices": None}))
        self.assertEqual(stream.check("12", {"choices": None}), "12")
        self.assertTrue(stream.same("$1,200.00", "1200") and stream.same("12 games", "12") and stream.same("Yes", "yes."))
        self.assertFalse(stream.same("March 3", "April 3"))
        self.assertEqual(stream.norm_key("Total Items!!"), "total_items")
        self.assertEqual(len(stream.norm_key("a" * 60)), 40)

    def test_handler_sandbox(self):
        case = {"question": "q", "choices": None, "table_for_pd": {"a": ["1", "2"]}}
        ok = "def solve(t, q, c):\n    print('noise')\n    return sum(map(int, t['a']))"
        self.assertEqual(stream.run_handler(ok, case), ("3", None))
        self.assertEqual(stream.run_handler("def solve(t, q, c):\n    while True: pass", case, timeout=1)[1], "timeout")
        self.assertIn("network", stream.run_handler("import socket\ndef solve(t,q,c):\n    socket.socket()", case)[1])

    def test_baseline_and_summary(self):
        run_all(self.tmp, self.d, self.lookup)
        out = os.path.join(self.tmp, "out")
        n = baseline.run(self.d, out, Fakes(self.lookup).large, n=40, last=15, log=lambda *_: None)
        self.assertGreater(n, 0)
        self.assertEqual(baseline.run(self.d, out, Fakes(self.lookup).large, n=40, last=15, log=lambda *_: None), 0)
        text = summarize.summarize(out, self.d, chunk_size=10, last=15)
        self.assertTrue(os.path.exists(os.path.join(out, "summary-e17.md")))
        for s in ("## Per chunk", "paired accuracy difference", "coverage below 30%", "total_items"):
            self.assertIn(s, text)


if __name__ == "__main__":
    unittest.main()
