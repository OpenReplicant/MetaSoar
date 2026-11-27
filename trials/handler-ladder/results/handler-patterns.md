# Handler patterns

Extracted 2026-11-26 from `intents.<key>.candidates.handler.code` in `results/state.json` (25 entries) and
`results-e17b/state.json` (27 entries). There is no `results-e17d/state.json` in this checkout. That makes 52 entries,
27 intents, and 32 distinct code strings. The counts below are "entries / distinct code strings".

## Repeated patterns

| Pattern | Entries / distinct | Where it went |
|---|---|---|
| Choice loop: match the answer against `choices` | 46 / 27 | `match_choice` |
| Number parser: `def num`, `nums`, `_parse_num`, `parse_num` (or inline) | 39 / 25 | `num` |
| Strip `$`, `,`, `%` before parsing | 32 / 19 | `num` |
| Strip unit words (units, kg, cars, dollars, people...) | 18 / 12 | `num` (letters removed) |
| Mentions "leaf" (stem-and-leaf tables) | 19 / 11 | `is_stem_leaf`, `stem_leaf_values` |
| Leaves split on comma | 19 / 11 | `stem_leaf_values` |
| Stem * 10 + leaf expansion | 17 / 9 | `stem_leaf_values` |
| Reads the "Leaf " key with a trailing space (or tries both spellings) | 13 / 7 | `is_stem_leaf` (names stripped) |
| Row label found in question text (`label.lower() in q`) | 14 / 9 | `row_by_label` |
| Threshold words: at least, more than, fewer than, ... | 10 / 6 | `threshold` |
| Label column = first non-numeric column | 8 / 4 | `label_column` |
| Numeric column = first column whose cells all parse | 6 / 3 | `numeric_columns` |
| Integer output when whole (`int(x) if x == int(x)`) | 15 / 10 | not added (one line) |
| Statistic keyword (median, mean, mode, range) | 8 / 4 | not added (see below) |
| Money format `f"${x:,.2f}"` | 6 / 4 | not added (one line) |
| `fractions.Fraction` for a ratio answer | 4 / 3 | not added (one line) |
| Shortage / surplus from demand and supply columns | 5 / 3 | not added (3 distinct, one intent family) |
| Clock time parsing (A.M. / P.M.) | 2 / 1 | `parse_time` |
| Question text decides a stem table (`"stem" in q`) | 3 / 2 | `is_stem_leaf` decides from the table |

## Stem-and-leaf handling, and what went wrong

- Stem-and-leaf is the largest shared cost. Most handlers that handle it repeat the expansion. Two different
  conventions appear. The standard reading, stem 2 with leaf 1 = 21, is in 17 / 9 handlers. Two entries
  (`count_people_interviewed_no`, in both state files) read stem 2 with leaf 1 as 2.1. That is wrong.
- `find_maximum_count` (r1_010 and r2_035) takes the stem-and-leaf path only if the question contains "stem" or
  "leaf". This is probably the handler that failed four times on stem-and-leaf tables (the task brief does not name it). A question such as "What is the largest number of roses?" on a
  stem-and-leaf table returns the leaf text of the largest stem, "7, 9", where the answer is 49. `find_maximum_rating_no`
  (r2_050) has the same question test.
- `count_people_interviewed` (r1_005 and r2_030) picks the first column whose cells parse as numbers. On a stem-and-leaf
  table that is the Stem column, so it counts stems, not values. On a constructed table it answered 0 for "at least 40",
  where the answer is 2.
- `count_people_interviewed_no` (r1_016 and r2_041) answered 0 for "at least 40", where the answer is 2.

These results come from running each distinct handler on one constructed stem-and-leaf table
(Stem 2, 3, 4; leaves "1, 6, 7", "2", "7, 9"). The checks are in the test file.

## Repeated helpers and the library

`handlers_lib.py` covers the patterns with the most entries: `num`, `numeric_columns`, `label_column`, `is_stem_leaf`,
`stem_leaf_values`, `parse_time`, `match_choice`, `row_by_label` and `threshold`. Nothing else was added. The statistic,
money-format and fraction patterns are one line each in the handlers that use them, and the shortage/surplus logic
appears in 3 distinct handlers for one question family. A helper for these would add API surface without saving much
code.
