"""Tests for E-17c's perturbations and read-only routing, with fake models: python3 -I -m unittest discover -s . -p 'test_*.py'"""
import json, os, random, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import perturb, test_stream  # noqa: E402

CASE = {"id": "1", "question": "Who has more, Ann or Bob?", "choices": ["Ann", "Bob", "Cyd"], "table_title": "T", "unit": None,
        "table": "Name | Count\nAnn | 3\nBob | 5\nCyd | 1", "table_for_pd": {"Name": ["Ann", "Bob", "Cyd"], "Count": ["3", "5", "1"]}}


class Small:
    def __init__(self, reply):
        self.reply = reply

    def ask(self, text, max_tokens):
        return self.reply


class T(unittest.TestCase):
    def test_shuffle_keeps_rows(self):
        v, _ = perturb.shuffle(CASE, random.Random(0))
        rows = v["table"].split("\n")[1:]
        self.assertNotEqual(rows, CASE["table"].split("\n")[1:])
        self.assertEqual(sorted(rows), sorted(CASE["table"].split("\n")[1:]))
        for r, a, b in zip(rows, v["table_for_pd"]["Name"], v["table_for_pd"]["Count"]):
            self.assertEqual(r, f"{a} | {b}")

    def test_rename_is_consistent(self):
        v, sub = perturb.rename(CASE, random.Random(0))
        m = {x: sub(x) for x in ("Ann", "Bob", "Cyd")}
        self.assertTrue(all(a != b for a, b in m.items()))
        self.assertEqual(v["question"], f"Who has more, {m['Ann']} or {m['Bob']}?")
        self.assertEqual(v["choices"], [m["Ann"], m["Bob"], m["Cyd"]])
        self.assertIn(f"{m['Bob']} | 5", v["table"])
        self.assertEqual(perturb.gold_for("Bob", sub), m["Bob"])
        self.assertEqual(perturb.gold_for("Bob's class", sub), m["Bob"] + "'s class")
        self.assertEqual(perturb.gold_for("7", sub), "7")
        self.assertIsNone(perturb.rename(dict(CASE, question="Who has more, ann or Bob?"), random.Random(0)))
        form = dict(CASE, table_for_pd={"Name": ["Ann", "Bob", "Cyd"], "Count": ["3", "", "1"]})
        self.assertIsNone(perturb.rename(form, random.Random(0)))
        self.assertIsNone(perturb.rename(dict(CASE, table_for_pd={"Year": ["2001", "2002"], "N": ["1", "2"]},
                                              table="Year | N\n2001 | 1\n2002 | 2"), random.Random(0)))

    def test_paraphrase_guard(self):
        self.assertIsNotNone(perturb.paraphrase(CASE, Small("Between Ann and Bob, who has the larger count?")))
        self.assertIsNone(perturb.paraphrase(CASE, Small("Who has more, Ann or Cyd?")))  # lost a label
        q = dict(CASE, question="How many more than 2 does Bob have?")
        self.assertIsNone(perturb.paraphrase(q, Small("How many more than 3 does Bob have?")))  # changed a number

    def test_run_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, lookup, _ = test_stream.build(tmp)
            out = os.path.join(tmp, "out")
            test_stream.run_all(tmp, d, lookup)
            before = open(os.path.join(out, "state.json")).read()
            f = test_stream.Fakes(lookup)
            perturb.run(out, d, f.large, f.small, n=40, start=30, log=lambda *_: None)
            self.assertEqual(open(os.path.join(out, "state.json")).read(), before)
            recs = [json.loads(x) for x in open(os.path.join(out, "perturb.jsonl"))]
            self.assertTrue(recs and {r["kind"] for r in recs} <= set(perturb.KINDS))
            self.assertTrue(any(not r["skipped"] and r["ok"] for r in recs))
            self.assertIn("E-17c verdict line", perturb.summary(out))


if __name__ == "__main__":
    unittest.main()
