"""Tests for the WTQ loader and scorer (E-18 preparation). Tiny made-up examples; no WTQ data and no models."""
import json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import smoke, stream, wtq, wtq_recurrence  # noqa: E402

TABLE = "Year\tTeam\tYear\t\nlist\\pitem\tA\\nB\t2001\tx\n1999\tRed  Sox\t2003\n2000\n"  # dup and empty headers, escapes, ragged row


def write_tree(root, n=6):
    """A miniature WTQ release: csv/200-csv/0.tsv and tagged/data/pristine-unseen-tables.tagged with n examples."""
    os.makedirs(os.path.join(root, "csv", "200-csv"))
    os.makedirs(os.path.join(root, "tagged", "data"))
    with open(os.path.join(root, "csv", "200-csv", "0.tsv"), "w", encoding="utf8") as f:
        f.write(TABLE)
    head = "id\tutterance\tcontext\ttargetValue\ttargetCanon\ttargetCanonType\n"
    rows = "".join(f"nu-{i}\twhich team in {1990 + i}?\tcsv/200-csv/0.csv\tRed Sox|1,000\tRed Sox|1000.0\tmixed\n" for i in range(n))
    with open(os.path.join(root, "tagged", "data", "pristine-unseen-tables.tagged"), "w", encoding="utf8") as f:
        f.write(head + rows)


class Loader(unittest.TestCase):
    def test_table_parse(self):
        cols, rows = wtq.parse_table(TABLE)
        self.assertEqual(cols, ["Year", "Team", "Year (2)", "col4"])
        self.assertEqual(rows, [["list|item", "A B", "2001", "x"], ["1999", "Red Sox", "2003", ""], ["2000", "", "", ""]])
        text, pd = wtq.table_case(cols, rows)
        self.assertEqual(text.split("\n")[0], "Year | Team | Year (2) | col4")
        self.assertEqual(text.split("\n")[2], "1999 | Red Sox | 2003 | ")
        self.assertEqual(pd["Team"], ["A B", "Red Sox", ""])
        self.assertTrue(all(isinstance(x, str) for v in pd.values() for x in v))

    def test_problem_and_runner_fields(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out:
            write_tree(root)
            wtq.build(root, out, {"test1k": ("pristine-unseen-tables", 5, 1)})
            with open(os.path.join(out, "problems_test1k.json")) as f:
                p = json.load(f)
            self.assertEqual(len(p), 5)
            one = p["nu-0"]
            self.assertEqual(one["answer"], ["Red Sox", "1,000"])
            self.assertEqual(one["answer_canon"], ["Red Sox", "1000.0"])
            self.assertIsNone(one["choices"]); self.assertIsNone(one["unit"]); self.assertIsNone(one["table_title"])
            # the runner's loader works unchanged and carries no gold
            cases = stream.load_cases(out, 5)
            self.assertEqual({c["id"] for c in cases}, set(p))
            for c in cases:
                self.assertEqual(set(c), {"id", *stream.PROBLEM_FIELDS})
            # the TabMWP prompt builder and the handler harness take these cases
            self.assertIn("Year | Team", smoke.prompt(cases[0]))
            ans, err = stream.run_handler("def solve(table, question, choices):\n    return table['Team'][1]", cases[0])
            self.assertEqual((ans, err), ("Red Sox", None))

    def test_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            write_tree(root)
            for o in (a, b):
                wtq.build(root, o, {"test1k": ("pristine-unseen-tables", 4, 18)})
            text = [open(os.path.join(d, "problems_test1k.json")).read() for d in (a, b)]
            self.assertEqual(text[0], text[1])

    def test_rules(self):
        op = wtq_recurrence.operation
        self.assertEqual(op("how many players scored at least 3 goals?"), "count")
        self.assertEqual(op("which nation won the most gold medals?"), "superlative")
        self.assertEqual(op("what is the difference in points between a and b?"), "difference")
        self.assertEqual(op("which is deeper, lake a or lake b?"), "comparison")
        self.assertEqual(op("what is the average attendance?"), "average")
        self.assertEqual(wtq_recurrence.fine("how many players scored at least 3 goals?", "count"), "count:condition")


class Scorer(unittest.TestCase):
    def test_numbers_and_units(self):
        self.assertTrue(wtq.score("17", ["17 years"], ["17.0"]))      # a bare number matches number plus unit words
        self.assertTrue(wtq.score("17 years", ["17 years"], ["17.0"]))
        self.assertTrue(wtq.score("17.0", ["17"], ["17.0"]))
        self.assertFalse(wtq.score("18", ["17"], ["17.0"]))
        self.assertTrue(wtq.score("100000", ["100,000"], ["100000.0"]))
        self.assertTrue(wtq.score("100,000", ["100,000"], ["100000.0"]))   # equal as strings
        self.assertFalse(wtq.score("100,000", ["100000"], ["100000.0"]))   # official: '100,000' is not a number

    def test_strings(self):
        self.assertTrue(wtq.score("José Alvarez (ESP)", ["Jose Alvarez"]))      # diacritics, a trailing (detail)
        self.assertTrue(wtq.score('"Red Sox"', ["red sox"]))                       # outer quotes, case
        self.assertTrue(wtq.score("Red Sox.", ["red sox"]))                        # final period
        self.assertFalse(wtq.score('"Red Sox".', ["red sox"]))                     # official order: the quotes go before the period
        self.assertTrue(wtq.score("Smith[1]", ["Smith"]))                          # a trailing citation
        self.assertTrue(wtq.score("a–b", ["a-b"]))                            # dashes
        self.assertFalse(wtq.score("Red Sox team", ["Red Sox"]))
        self.assertFalse(wtq.score(None, ["x"]))

    def test_lists_are_sets(self):
        gold = ["Italy", "France", "Spain"]
        self.assertTrue(wtq.score(["Spain", "Italy", "France"], gold))
        self.assertTrue(wtq.score("Spain, Italy, France", gold))
        self.assertTrue(wtq.score("Spain | Italy | France", gold))
        self.assertTrue(wtq.score("Spain\nItaly\nFrance", gold))
        self.assertTrue(wtq.score("Spain, Italy and France", gold))
        self.assertFalse(wtq.score("Spain, Italy", gold))                          # sizes differ
        self.assertFalse(wtq.score("Spain, Italy, France, Peru", gold))
        self.assertTrue(wtq.score(["a", "a", "b"], ["a", "b"]))                    # duplicates collapse, as official

    def test_comma_inside_one_item(self):
        self.assertTrue(wtq.score("Paris, France", ["Paris, France"]))            # whole text first
        self.assertFalse(wtq.score("Paris, France", ["Paris"]))

    def test_dates(self):
        self.assertTrue(wtq.score("1990-01-12", ["January 12, 1990"], ["1990-01-12"]))
        self.assertFalse(wtq.score("xx-01-12", ["January 12, 1990"], ["1990-01-12"]))   # 'xx' fields must match too
        self.assertTrue(wtq.score("xx-01-12", ["January 12"], ["xx-01-12"]))
        self.assertTrue(wtq.score("January 12, 1990", ["January 12, 1990"], ["1990-01-12"]))  # equal as strings
        self.assertFalse(wtq.score("12 January 1990", ["January 12, 1990"], ["1990-01-12"]))  # official: not a date

    def test_year_only_date_is_a_number(self):
        self.assertTrue(wtq.score("1990", ["1990"], ["1990-xx-xx"]))
        self.assertTrue(wtq.score("1990.0", ["1990"], ["1990-xx-xx"]))

    def test_correct_takes_a_problem(self):
        p = {"answer": ["Red Sox", "1,000"], "answer_canon": ["Red Sox", "1000.0"]}
        self.assertTrue(wtq.correct("1000, red sox", p))
        self.assertFalse(wtq.correct("red sox", p))
        self.assertTrue(wtq.correct("5", {"answer": "5"}))   # a plain string gold, as TabMWP's file has

    def test_differences_from_smoke_correct(self):
        """Where `smoke.correct` (TabMWP's scorer) and the WTQ scorer disagree."""
        tab = lambda g: {"answer": g, "ans_type": "integer_number"}
        # smoke strips $ , and units and reads the first number; WTQ's string rule is stricter
        self.assertTrue(smoke.correct("1,000 people", tab("1000")))
        self.assertFalse(wtq.score("1,000 people", ["1000"], ["1000.0"]))
        self.assertTrue(smoke.correct("about 3", tab("3")))
        self.assertFalse(wtq.score("about 3", ["3"], ["3.0"]))
        # lists: smoke has one answer; WTQ compares sets
        self.assertFalse(smoke.correct("b, a", {"answer": "a, b", "ans_type": "other"}))
        self.assertTrue(wtq.score("b, a", ["a", "b"]))
        # smoke is case-folded text; WTQ also drops diacritics, (details) and citations
        self.assertFalse(smoke.correct("Jose", {"answer": "José", "ans_type": "other"}))
        self.assertTrue(wtq.score("Jose", ["José"]))


if __name__ == "__main__":
    unittest.main()
