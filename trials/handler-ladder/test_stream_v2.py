"""Tests for E-17d's rules (stream_v2.py), with fake models: python3 -I -m unittest discover -s . -p 'test_*.py'"""
import json, math, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stream, stream_v2, test_stream  # noqa: E402

KW = ("total", "most", "difference")


def fake_embed(texts):
    out = []
    for t in texts:
        v = [1.0 if k in t else 0.0 for k in KW] + [0.1]
        n = math.sqrt(sum(x * x for x in v))
        out.append([x / n for x in v])
    return out


def fake_choose(question, options):
    k = next(w for w in KW if w in question)
    hit = next((o for o, q in options.items() if k in q), None)
    p = {o: 0.0 for o in options} | {"none": 0.0}
    p[hit or "none"] = 0.9
    return p


def v2(tmp, d, fakes, out="v2", n=40):
    return stream_v2.StreamV2(d, os.path.join(tmp, out), fakes.large, fakes.small, chunk_size=10, n=n,
                              log=lambda *_: None, embed_fn=fake_embed, choose_fn=fake_choose)


class T(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.d, self.lookup, self.na = test_stream.build(self.tmp)

    def tearDown(self):
        self._t.cleanup()

    def test_wilson(self):
        self.assertLess(stream_v2.wilson_lower(3, 3), 0.5)
        self.assertLess(stream_v2.wilson_lower(8, 8), stream_v2.LOWER)
        self.assertGreaterEqual(stream_v2.wilson_lower(9, 9), stream_v2.LOWER)
        self.assertLess(stream_v2.wilson_lower(9, 10), stream_v2.LOWER)

    def test_strict_check(self):
        c = {"choices": None}
        for bad in ("None", "n/a", "<the answer only>", '<the answer only>"', "0, 0, 6, 8, 8", "x" * 120):
            self.assertIsNone(stream_v2.strict(bad, c), bad)
        for good in ("1,471", "$23,690.00", "12", "swing dance class", "3/4"):
            self.assertEqual(stream_v2.strict(good, c), good)

    def test_shapes(self):
        stem = {"table_for_pd": {"Stem": ["3", "4"], "Leaf ": ["1, 6, 7", "2"]}, "choices": None}
        plain = {"table_for_pd": {"Person": ["Ann", "Bob"], "N": ["7", "8"]}, "choices": None}
        self.assertNotEqual(stream_v2.shape(stem), stream_v2.shape(plain))
        self.assertEqual(stream_v2.shape(plain), "2:text,num:open")

    def test_end_to_end(self):
        f = test_stream.Fakes(self.lookup)
        s = v2(self.tmp, self.d, f)
        for c in (1, 2, 3, 4):
            s.run_chunk(c)
        recs = s.state["cases"]
        intents = {r["intent"] for r in recs}
        self.assertEqual(len(intents), 3, intents)  # d1 merges by kind; no duplicate keys
        self.assertTrue(all(r["route"]["by"] in ("d1", "new") for r in recs))
        self.assertEqual(sum(r["route"]["by"] == "new" for r in recs), 3)
        h = s.state["intents"][recs[0]["intent"]]["candidates"]["handler"]
        cands = [c for it in s.state["intents"].values() for c in it["candidates"].values() if c and c["status"] == "active"]
        self.assertTrue(cands)
        for c in cands:  # promoted only on evidence
            self.assertGreaterEqual(stream_v2.wilson_lower(c["agree"], c["n"]), stream_v2.LOWER)
            self.assertTrue(c["shapes"])
        first_cheap = next(i for i, r in enumerate(recs) if r["rung"] != "large")
        self.assertGreaterEqual(first_cheap, 9)  # no cheap answer before 9 agreements are possible
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "v2", "vectors.json")))

    def test_unseen_shape_goes_large(self):
        f = test_stream.Fakes(self.lookup)
        s = v2(self.tmp, self.d, f)
        for c in (1, 2, 3):
            s.run_chunk(c)
        it = next(it for it in s.state["intents"].values() if it["candidates"]["handler"] and it["candidates"]["handler"]["status"] == "active")
        case = s.byid[it["labelled"][-1]["id"]]
        odd = dict(case, table_for_pd={k: v + ["1, 2"] for k, v in case["table_for_pd"].items()})
        self.assertEqual(s.decide_apply(odd, it)[0], "large")
        self.assertNotEqual(s.decide_apply(case, it)[0], "large")

    def test_rejudge_v1_state(self):
        test_stream.run_all(self.tmp, self.d, self.lookup, "v1")  # v1 rules: promotions on 3 of 3
        s = v2(self.tmp, self.d, test_stream.Fakes(self.lookup), out="v1")
        self.assertEqual(s.state["rules"], "v2")
        for it in s.state["intents"].values():
            for c in it["candidates"].values():
                if c and c["status"] == "active":
                    self.assertGreaterEqual(stream_v2.wilson_lower(c["agree"], c["n"]), stream_v2.LOWER)
                if c and "v1_status" in c:
                    self.assertTrue(all(x["id"] not in c["used"] for x in c["failures"]))

    def test_no_gold(self):
        with open(os.path.join(HERE, "stream_v2.py")) as f:
            src = f.read()
        for banned in ("ans_type", "ques_type", "smoke.correct", '"solution"', 'get("answer")', "problems_test1k"):
            self.assertFalse(banned in src, banned)


if __name__ == "__main__":
    unittest.main()
