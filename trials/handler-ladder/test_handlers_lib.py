"""Tests for handlers_lib, and for the five rewritten handlers against the original code in results/state.json."""
import json
import os
import unittest

from handlers_lib import (is_stem_leaf, label_column, match_choice, num, numeric_columns, parse_time, row_by_label,
                          stem_leaf_values, threshold)
import handlers_rewritten as new

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "results", "state.json")

STEM = {"Stem": ["2", "3", "4"], "Leaf ": ["1, 6, 7", "2", "7, 9"]}


class NumTests(unittest.TestCase):
    def test_money_and_units(self):
        self.assertEqual(num("$1,250.50"), 1250.5)
        self.assertEqual(num("$3"), 3.0)
        self.assertEqual(num("5 cars"), 5.0)
        self.assertEqual(num("12 units"), 12.0)
        self.assertEqual(num("45%"), 45.0)
        self.assertEqual(num(" 4 "), 4.0)
        self.assertEqual(num(7), 7.0)

    def test_fractions(self):
        self.assertEqual(num("1/2"), 0.5)
        self.assertEqual(num("2 1/2"), 2.5)
        self.assertEqual(num("-1/4"), -0.25)
        self.assertEqual(num("-1 1/2"), -1.5)
        self.assertEqual(num("1/2 cup"), 0.5)
        self.assertIsNone(num("3/0"))

    def test_none_for_times_text_and_lists(self):
        self.assertIsNone(num("11:15 A.M."))
        self.assertIsNone(num("2.10 P.M."))
        self.assertIsNone(num("1, 6, 7"))
        self.assertIsNone(num("abc"))
        self.assertIsNone(num(""))
        self.assertIsNone(num("-"))


class ColumnTests(unittest.TestCase):
    def test_numeric_columns(self):
        t = {"Name": ["Ann", "Bo"], "Score": ["3", "4.5"], "Cost": ["$2", "$1,000"], "Cells": ["1, 6", "2"]}
        self.assertEqual(numeric_columns(t), ["Score", "Cost"])

    def test_numeric_columns_ignores_empty_cells(self):
        self.assertEqual(numeric_columns({"x": ["1", "", "2"], "y": ["", ""]}), ["x"])

    def test_label_column(self):
        self.assertEqual(label_column({"Day": ["Mon"], "Cups": ["3"]}), "Day")
        self.assertEqual(label_column({"Cups": ["3"], "Day": ["Mon"]}), "Day")
        self.assertEqual(label_column({"a": ["1"], "b": ["2"]}), "a")
        self.assertIsNone(label_column({}))


class StemLeafTests(unittest.TestCase):
    def test_is_stem_leaf_names_and_cells(self):
        self.assertTrue(is_stem_leaf(STEM))
        self.assertTrue(is_stem_leaf({"Stem": ["2"], "Leaf": ["1"]}))
        self.assertTrue(is_stem_leaf({"stem": ["2"], "leaf": ["1"]}))
        self.assertTrue(is_stem_leaf({"Leaf ": ["1, 6"], "Stem ": ["2"]}))

    def test_is_stem_leaf_rejects_other_tables(self):
        self.assertFalse(is_stem_leaf({"Day": ["Mon"], "Cups": ["3"]}))
        self.assertFalse(is_stem_leaf({"Stem": ["2"], "Leaf ": ["1 6"]}))      # no commas
        self.assertFalse(is_stem_leaf({"Stem": ["2a"], "Leaf ": ["1"]}))       # stem not a whole number
        self.assertFalse(is_stem_leaf({"Stem": ["2"], "Leaf ": ["1"], "X": ["3"]}))
        self.assertFalse(is_stem_leaf({"Stem": ["2", "3"], "Leaf ": ["1"]}))   # lengths differ
        self.assertFalse(is_stem_leaf({}))

    def test_stem_leaf_values(self):
        self.assertEqual(stem_leaf_values(STEM), [21, 26, 27, 32, 47, 49])
        self.assertEqual(stem_leaf_values({"Stem": ["5"], "Leaf": ["0"]}), [50])

    def test_stem_leaf_values_empty_for_other_tables(self):
        self.assertEqual(stem_leaf_values({"Day": ["Mon"], "Cups": ["3"]}), [])


class TimeTests(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(parse_time("11:15 A.M."), 675)
        self.assertEqual(parse_time("2.10 P.M."), 850)
        self.assertEqual(parse_time("12:30 A.M."), 30)
        self.assertEqual(parse_time("12:00 P.M."), 720)
        self.assertEqual(parse_time("9:05 a.m."), 545)
        self.assertEqual(parse_time("11:15 AM"), 675)
        self.assertEqual(parse_time("14:05"), 845)

    def test_parse_time_rejects_bad_input(self):
        self.assertIsNone(parse_time("12:60 P.M."))
        self.assertIsNone(parse_time("13:00 P.M."))
        self.assertIsNone(parse_time("0:30 A.M."))
        self.assertIsNone(parse_time("abc"))


class ChoiceTests(unittest.TestCase):
    def test_text_match_ignores_case(self):
        self.assertEqual(match_choice("yes", ["Yes", "No"]), "Yes")

    def test_number_match_by_value(self):
        self.assertEqual(match_choice("12", ["10", "12"]), "12")
        self.assertEqual(match_choice("$3.5", ["$3.50", "$4"]), "$3.50")
        self.assertEqual(match_choice("1/2", ["0.5", "1"]), "0.5")

    def test_no_match(self):
        self.assertIsNone(match_choice("9", ["10", None]))
        self.assertIsNone(match_choice("x", None))
        self.assertIsNone(match_choice("x", []))


class RowTests(unittest.TestCase):
    T = {"Item": ["pencil", "notebook", "green apple", "apple", "berry", "bunch"],
         "Price": ["1", "2", "3", "4", "5", "6"]}

    def test_row_found_in_question(self):
        self.assertEqual(row_by_label(self.T, "How much do 2 pencils cost?"), 0)
        self.assertEqual(row_by_label(self.T, "Cost of A NOTEBOOK?"), 1)

    def test_plurals(self):
        self.assertEqual(row_by_label(self.T, "Two green apples"), 2)  # longest label wins over "apple"
        self.assertEqual(row_by_label(self.T, "the apple"), 3)
        self.assertEqual(row_by_label(self.T, "How many berries?"), 4)
        self.assertEqual(row_by_label(self.T, "bunches of bananas"), 5)

    def test_whole_words_only(self):
        self.assertIsNone(row_by_label({"Item": ["cat"], "Price": ["1"]}, "concatenate"))
        self.assertIsNone(row_by_label(self.T, "How many bananas?"))


class ThresholdTests(unittest.TestCase):
    def test_comparisons(self):
        at_least_40 = threshold("How many had at least 40?")
        self.assertTrue(at_least_40(40))
        self.assertFalse(at_least_40(39))
        more_than_35 = threshold("more than 35")
        self.assertFalse(more_than_35(35))
        self.assertTrue(more_than_35(36))
        less_than_5 = threshold("less than 5")
        self.assertTrue(less_than_5(4))
        self.assertFalse(less_than_5(5))
        self.assertTrue(threshold("at most 5")(5))
        self.assertTrue(threshold("fewer than 3 people")(2))
        self.assertTrue(threshold("no more than 4")(4))
        self.assertFalse(threshold("no more than 4")(5))
        self.assertTrue(threshold("less than or equal to 5")(5))
        self.assertFalse(threshold("less than or equal to 5")(6))
        self.assertTrue(threshold("no fewer than 2")(2))
        self.assertTrue(threshold("over 10")(11))

    def test_no_comparison(self):
        self.assertIsNone(threshold("How many people were there?"))


class ApiTests(unittest.TestCase):
    def test_exported_names_are_documented_functions(self):
        import handlers_lib
        for name in handlers_lib.__all__:
            fn = getattr(handlers_lib, name)
            self.assertTrue(callable(fn), name)
            self.assertTrue(fn.__doc__, name)


def original(intent):
    """The handler stored in results/state.json for this intent, as a solve function."""
    with open(STATE) as f:
        code = json.load(f)["intents"][intent]["candidates"]["handler"]["code"]
    ns = {}
    exec(compile(code, intent, "exec"), ns)
    return ns["solve"]


@unittest.skipUnless(os.path.exists(STATE), "results/state.json is not in this checkout")
class RewriteTests(unittest.TestCase):
    PRICES = {"Item": ["pencil", "notebook", "ruler"], "Price": ["$0.50", "$2.25", "$1.10"]}
    COUNTS = {"Score": ["1", "2", "3"], "Frequency": ["4", "2", "5"]}
    FIRST = {"Store": ["Ann", "Bo", "Cy"], "Sales": ["$12", "5 cars", "9"]}
    DAYS = {"Day": ["Mon", "Tue", "Wed"], "Cups": ["3", "10", "7"]}
    STEM_COUNTS = {"Stem": ["3", "4"], "Leaf ": ["1, 6, 7", "2"]}

    def check(self, intent, fn, cases):
        """Same answer as the original on each case; returns the new answers for further checks."""
        old = original(intent)
        out = []
        for table, question, choices in cases:
            got = fn(table, question, choices)
            want = old(table, question, choices)
            self.assertEqual(got, want, f"{intent}: {question!r}")
            out.append(got)
        return out

    def test_find_minimum_count(self):
        got = self.check("find_minimum_count", new.find_minimum_count, [
            (self.FIRST, "Which store had the fewest sales?", None),
            (self.FIRST, "Which store had the most sales?", None),
            (self.FIRST, "Which store had the fewest sales?", ["Ann", "Bo", "Cy"]),
            (STEM, "What is the least number of members?", None),
            (STEM, "What is the least value?", ["21", "30", "49"]),
        ])
        self.assertEqual(got[0], "Bo")
        self.assertEqual(got[1], "Ann")
        self.assertEqual(got[3], "21 members")

    def test_compute_max_count(self):
        got = self.check("compute_max_count", new.compute_max_count, [
            (STEM, "What is the largest number of roses?", None),
            (STEM, "What is the largest number of roses?", ["47", "49", "50"]),
        ])
        self.assertEqual(got, ["49", "49"])

    def test_find_maximum_count(self):
        got = self.check("find_maximum_count", new.find_maximum_count, [
            (self.DAYS, "On which day did the most cups sell?", None),
            (self.DAYS, "On which day did the smallest number of cups sell?", None),
            (self.DAYS, "Which day had the most?", ["Mon", "Tue", "Wed"]),
        ])
        self.assertEqual(got, ["Tue", "Mon", "Tue"])

    def test_find_maximum_count_stem_leaf_without_the_word_stem(self):
        # The original took its stem-and-leaf path only when the question said "stem" or "leaf": here it returned "7, 9".
        question = "What is the largest number of roses?"
        self.assertNotEqual(original("find_maximum_count")(STEM, question, None), "49")
        self.assertEqual(new.find_maximum_count(STEM, question, None), "49")
        self.assertEqual(new.find_maximum_count(STEM, "What is the smallest number of roses?", None), "21")

    def test_count_people_interviewed_no(self):
        got = self.check("count_people_interviewed_no", new.count_people_interviewed_no, [
            (self.COUNTS, "How many people scored at least 2?", None),
            (self.COUNTS, "How many people scored more than 1?", None),
            (self.COUNTS, "How many people scored less than 3?", None),
            (self.COUNTS, "How many people scored at most 2?", None),
            (self.COUNTS, "How many people scored at least 2?", ["7", "9"]),
        ])
        self.assertEqual(got, ["7", "7", "6", "6", "7"])

    def test_count_people_interviewed_no_stem_leaf(self):
        # Values are 31, 36, 37, 42. The original read them as 3.1, 3.6, 3.7, 4.2 and got 0, 0 and 3.
        question_ge = "How many people had at least 40?"
        self.assertNotEqual(original("count_people_interviewed_no")(self.STEM_COUNTS, question_ge, None), "1")
        self.assertEqual(new.count_people_interviewed_no(self.STEM_COUNTS, question_ge, None), "1")
        self.assertEqual(new.count_people_interviewed_no(self.STEM_COUNTS, "How many people had more than 35?", None), "3")
        self.assertEqual(new.count_people_interviewed_no(self.STEM_COUNTS, "How many people had fewer than 35?", None), "1")

    def test_compute_total_cost(self):
        got = self.check("compute_total_cost", new.compute_total_cost, [
            (self.PRICES, "How much would it cost to buy a notebook and a ruler?", None),
            (self.PRICES, "How much would it cost to buy 2 pencils and a ruler?", ["$1.00", "$3.20", "$4.00"]),
            (self.PRICES, "How much would it cost to buy 3 notebooks?", None),
        ])
        self.assertEqual(got, ["$3.35", "$3.20", "$6.75"])


if __name__ == "__main__":
    unittest.main()
