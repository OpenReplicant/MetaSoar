"""Tests for E-19's operations (ops.py), parser helpers (parse.py) and runner (stream_v4.py), with fake models:
python3 -I -m unittest discover -s . -p 'test_*.py'"""
import json, os, random, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ops, parse, stream_v4  # noqa: E402

T = {"Date": ["March 2011", "May 2012", "June 2013", "July 2014", "Total"],
     "Team": ["Arc", "Bel", "Cor", "Dun", "Total"],
     "Time": ["2:01.10", "2:03.14", "1:59.00", "2:00.00", ""],
     "Pts": ["5", "8", "3", "9", "25"],
     "League": ["Div 2", "Div 1", "Div 1", "Div 1", ""]}


def run(**prog):
    return ops.run(T, prog)


class Ops(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(run(op="count", column="Team", where=[{"column": "Date", "is": ">", "value": "2011"}]), "3")
        self.assertEqual(run(op="argmax", column="Date"), "July 2014")
        self.assertEqual(run(op="argmin", column="Team", by="Date"), "Arc")
        self.assertEqual(ops.date_value("2000–01"), 20000000)
        self.assertGreater(ops.date_value("March 4, 2012"), ops.date_value("February 28, 2012"))

    def test_durations(self):
        self.assertEqual(run(op="difference", column="Time", key="Team", items=["Arc", "Bel"]), "2.04")
        self.assertEqual(run(op="argmin", column="Team", by="Time"), "Cor")
        self.assertEqual(ops.duration("2.04 seconds"), 2.04)
        self.assertEqual(ops.duration("1:02:03"), 3723)

    def test_summary_row_left_out(self):
        self.assertEqual(run(op="sum", column="Pts"), "25")  # 5 + 8 + 3 + 9, not counting "Total"
        self.assertEqual(run(op="argmax", column="Team", by="Pts"), "Dun")
        self.assertEqual(run(op="count", column="Team"), "4")
        self.assertEqual(run(op="value", column="Pts", where=[{"column": "Team", "is": "=", "value": "Total"}]), "25")

    def test_compare(self):
        c = dict(op="compare", column="Pts", key="Team")
        self.assertEqual(run(**c, items=["Arc", "Bel"], answer_as="more_less"), "less")
        self.assertEqual(run(**c, items=["Arc", "Bel"], direction="greater", answer_as="yes_no"), "no")
        self.assertEqual(run(**c, items=["Arc", "Bel"], direction="less", answer_as="yes_no"), "yes")
        self.assertEqual(run(**c, items=["Arc", "Bel"], answer_as="item"), "Bel")
        self.assertEqual(run(**c, items=["Arc", "Bel"], direction="less", answer_as="item"), "Arc")
        self.assertEqual(run(**c, items=["Bel"], than="6", answer_as="above_below"), "above")
        self.assertEqual(run(op="compare", column="Date", key="Team", items=["Arc", "Cor"], answer_as="before_after"),
                         "before")
        self.assertEqual(run(op="compare", column="Date", key="Team", items=["Dun"], than="2013", direction="greater"),
                         "yes")
        self.assertEqual(run(**c, items=["Arc", "Arc"], direction="equal", answer_as="yes_no"), "yes")

    def test_consecutive(self):
        self.assertEqual(run(op="consecutive", column="Team",
                             where=[{"column": "League", "is": "=", "value": "Div 1"}]), "3")
        with self.assertRaises(ops.Unsupported):
            run(op="consecutive", column="Team", where=[{"column": "League", "is": "=", "value": "Div 9"}])

    def test_unsupported(self):
        for prog in ({"op": "count", "where": [{"column": "Nope", "is": "=", "value": "x"}]},
                     {"op": "value", "column": "Team", "where": [{"column": "Team", "is": "=", "value": "Zed"}]},
                     {"op": "compare", "column": "Team", "key": "Team", "items": ["Arc", "Bel"]},
                     {"op": "fly"}):
            with self.assertRaises(ops.Unsupported):
                ops.run(T, prog)


class Parser(unittest.TestCase):
    def test_schema_and_guide(self):
        s = parse.schema(list(T), "comparison")
        self.assertIn("compare", s["properties"]["op"]["enum"])
        self.assertEqual(s["properties"]["items"]["minItems"], 1)
        self.assertNotIn("consecutive", parse.guide("comparison"))
        self.assertIn("consecutive", parse.guide("count"))
        for cols, rows, q, prog in parse.SEEDS:  # every seed runs on its own two rows
            ops.run({c: [r[i] for r in rows] for i, c in enumerate(cols)}, prog)

    def test_vote_and_name_one(self):
        agree = stream_v4.agree_form
        self.assertEqual(parse.vote(["5", "5 years", "6", None], agree), ("5", 2))
        self.assertEqual(parse.vote([None, None], agree), (None, 0))
        case = {"question": "name one team in div 1", "table_for_pd": T}
        a, _, why = parse.evaluate(case, json.dumps({"op": "value", "column": "Team",
                                                     "where": [{"column": "League", "is": "=", "value": "Div 1"}]}))
        self.assertEqual((a, why), ("Bel", "ok"))
        self.assertEqual(parse.evaluate(case, "{not json")[2], "bad json")


def build(root, n=40):
    rng = random.Random(0)
    probs = {}
    for i in range(n):
        rows = 3 + i % 3
        names = [f"T{i}x{j}" for j in range(rows)]
        probs[str(7000 + i)] = {"question": f"How many teams are listed (case {i})?", "choices": None, "table_title": None,
                                "unit": None, "table": "", "table_for_pd": {"Team": names, "Pts": [str(rng.randint(1, 9)) for _ in names]},
                                "answer": [str(rows)], "answer_type": "x", "table_id": f"t{i}"}
    d = os.path.join(root, "data")
    os.makedirs(d)
    json.dump(probs, open(os.path.join(d, "problems_test1k.json"), "w"))
    return d


class Runner(unittest.TestCase):
    def test_voting_and_think_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = build(tmp)
            cases = {c["id"]: c for c in stream_v4.stream.load_cases(d, 40)}
            e18 = os.path.join(tmp, "e18")
            os.makedirs(e18)
            with open(os.path.join(e18, "stream.jsonl"), "w") as f:
                for i, c in enumerate(cases.values()):
                    f.write(json.dumps({"id": c["id"], "class": "count", "rung": "large", "chunk": 1 + i // 20,
                                        "answer": str(len(c["table_for_pd"]["Team"]))}) + "\n")
            calls = {"think": 0}

            def small(text, cols, cls, temperature=0, seed=None):  # greedy right; samples split 2 right, 2 wrong
                if temperature == 0 or seed in (1, 2):
                    return json.dumps({"op": "count", "column": "Team"}), {}
                return json.dumps({"op": "sum", "column": "Pts"}), {}

            def think(text, cols, cls):
                calls["think"] += 1
                return json.dumps({"op": "count", "column": "Team"}), {"thinking_tokens": 42}

            s = stream_v4.StreamV4(d, os.path.join(tmp, "out"), lambda *a: ("", {}), small,
                                   embed_fn=lambda texts: [[1.0, 0.0] for _ in texts], log=lambda *_: None,
                                   total=40, k=5, m=3, think_fn=think)
            s.replay(e18, n=40)
            recs = s.state["cases"]
            self.assertTrue(all(r["votes"] == 3 and len(r["samples"]) == 5 for r in recs))
            self.assertTrue(all(r["agreed"] for r in recs))
            self.assertEqual(calls["think"], 0)  # the greedy program agreed everywhere: the arm never runs
            c = s.state["classes"]["count"]
            self.assertEqual((c["n"], c["agree"]), (40, 40))
            self.assertEqual(c["status"], "active")

            s2 = stream_v4.StreamV4(d, os.path.join(tmp, "out2"), lambda *a: ("", {}),
                                    lambda *a, **k: (json.dumps({"op": "sum", "column": "Pts"}), {}),
                                    embed_fn=lambda texts: [[1.0, 0.0] for _ in texts], log=lambda *_: None,
                                    total=40, k=5, m=5, think_fn=think)
            s2.replay(e18, n=10)
            r = s2.state["cases"][0]
            self.assertEqual(calls["think"], 10)
            self.assertTrue(r["think"]["agreed"])
            self.assertEqual(r["think"]["thinking_tokens"], 42)
            self.assertEqual(s2.state["classes"]["count"]["n"] + s2.state["classes"]["count"]["abstain"], 10)


if __name__ == "__main__":
    unittest.main()
