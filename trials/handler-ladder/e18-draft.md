# E-18 draft registration: the handler ladder on WikiTableQuestions

A proposal for the owner to review. It is not in `docs/experiments.md`. Nothing here has been run on a model. The numbers
come from `results/wtq-recurrence.md` (rules and counts, no model) and from the files named.

## Proposed row

| ID | Claim | Falsifier | Setup | Tells us | Status |
| --- | --- | --- | --- | --- | --- |
| E-18 | **On tables and questions that are not templated, the ladder still answers a large share of cases without the large model, when a handler is shared across a coarse operation class and gated by a loose table shape.** On WikiTableQuestions (WTQ; Pasupat and Liang, ACL 2015; CC BY-SA 4.0), a stream of 450 `test1k` cases (the first 450 of the runner's fixed order), in chunks of 50, with the E-17d rules and two changes: intents at two levels (a coarse operation class, then a fine intent under it), and a loose table shape (columns by number, and by numeric or text) in place of E-17d's exact shape. Measured on cases 301 to 450. | over cases 301 to 450, templates and handlers answer under 30%; or accuracy is more than 2 points below the large model alone on the same cases (paired, 95% bootstrap interval: its upper end below -2); or `stream.py`, `stream_v2.py` or `wtq.py` changed between this registration and the run | WTQ v1.0.2 at `84dd647e7a2b47661e990c490d63b49d0b84c42a` (fetched by `wtq.py fetch`, not committed; SHA-256 of the zip `7c9ca7cc...`); `problems_test1k.json` for the stream, `problems_dev1k.json` for prompts and the smoke test; Inkling and LFM3 as in E-17 (`serve.sh ladder`), d1-2B and the embedder on the CPU (`serve.sh elabcpu`); the large model's accuracy and speed on WTQ measured first (below) | whether E-17's result holds when intents are fuzzy and tables vary (the owner: E-18 is "a task family that is not templated", `docs/handler-ladder.md`, Experiments); whether a handler can be shared across table schemas, which E-17b showed it could not at fine intents and exact shapes | proposed |

The falsifier has the form of E-17d's. Its 30% is checked against what the data allows, below.

## Reported, not part of the falsifier

- Accuracy on the cases the exact shape would have admitted, and on those only the loose shape admitted. This is the cost of the looser gate.
- Per class: cases, cheap answers, accuracy, handler promotions, demotions.
- Inkling calls, Inkling seconds and wall seconds a case, against the last chunk of E-17d.
- The share of cases the large model answered because a handler raised or failed a check.
- Intents: the number of classes and fine intents, and those seen once.

## Why a loose shape, and what the data allows

`results/wtq-recurrence.md`, on the same 450 cases, assuming a handler is written and promoted on time and is right
(12 cases of its key first: 3 to write from, 9 agreements):

| Cases 301 to 450 | No shape gate | Exact shape gate (E-17d) | Loose shape gate (proposed) |
| --- | --- | --- | --- |
| by operation class | 92.7% | 32.0% | 55.3% |
| by fine class | 89.3% | 24.0% | 47.3% |

With E-17d's exact shape, the most any handler could answer is 32% at the coarse level and 24% at the fine level, against
a falsifier of under 30%. The falsifier would then be decided by the gate, not by the ladder. With the loose shape the
ceiling is 47% to 55%, so 30% needs a bit over half of it. A smaller window shows the same order: cases 151 to 300 have
ceilings of 22.7% (exact) and 44.7% (loose) by class. This is why the stream is 450 cases, not 300.

The loose shape guards less. E-17b's failures were handlers on table shapes they had not seen, and E-17d's exact shape
was the fix. Two things stand in for it: a handler must raise (so the case falls back) when it cannot find the columns
the question names by header or cell text, and the report above splits accuracy by exact-shape novelty. If accuracy on
loose-only cases is much lower than on exact-shape cases, the registered result stands but the draft's claim about the
loose gate is not supported, and the summary says so.

## The stream

- 450 cases, chunks of 50 (9 chunks): `stream.stream_ids` order (sorted ids, `random.Random(17)` shuffle) of `problems_test1k.json`. The recurrence figures above use the same order.
- Time. The large model took about 22 s a case on TabMWP (E-17). That is 2.75 hours for 450 if it answered all of them, and the ladder is meant to use it less. Handlers take 45 to 120 s each to write (`docs/handler-ladder.md`); about 10 classes, some rewritten once, is under an hour (an estimate). WTQ tables are large (median 1,214 characters, 90th percentile 3,890, maximum 26,534 in the first 600 cases), so reading them may be slower than TabMWP's. This is not measured. The smoke test below measures it.
- Measured on cases 301 to 450, as E-17b and E-17d. The large model alone is run on the last 150 cases a cheaper rung answered (`baseline.py`, resumable), for the paired difference.
- Prompt size. Inkling's window on `serve.sh ladder` is 16,384 tokens. A handler prompt holds 3 examples with the table as JSON. 5% of the first 600 cases have a JSON table over 10,000 characters, so 3 such examples could not fit. The new runner picks the 3 labelled cases of shortest table for the examples.

## Before the stream: the large model on WTQ

A smoke test as `smoke.py`'s: 40 `dev1k` cases, Inkling alone, scored by `wtq.correct`, with the time per case. Run first. Two
conditions, to be set by the owner before the run (a proposal, with no source behind the figures):
- If Inkling's accuracy is under 50%, do not run E-18. Promotion is by agreement with Inkling's answers, so below half the ladder would be learning mostly wrong labels, and E-18 would measure agreement on errors.
- If a case takes over 40 s, cut the stream to 300 and say so; the ceilings above for 300 are 44.7% (loose) in cases 151 to 300.

`smoke.py` itself reads `p["ans_type"]` in `correct` and the TabMWP data path; run it with a copy that calls `wtq.correct` (a new file, `smoke_wtq.py`, in the run's commit).

## Two-level intents

**Coarse level: a closed set of operation classes.** About 8 from the rules in `wtq_recurrence.py`: count, superlative,
ordinal, comparison (between named entities), neighbour (the row before or after), difference, sum, average, and lookup
as the catch-all. The rules are a guide to the set, not the classifier: they are rough (the author read 30 random questions
and found 27 plausible, 3 doubtful). The classifier is d1-2B choosing among the classes, each shown by its first question,
with "none of these" (E-17d's mechanism, on a closed list; `d1_intent.d1_choose`). Its instruction text names "a math word
problem", so the new runner sets its own text. A "none" goes to a class `other`, which is never promoted.

**Fine level: E-17d's intents inside a class.** The nearest 6 known fine intents of the question's class by embedding, d1-2B
choosing among them, the small model naming a new one. Examples: `count:condition`, `count:plain`, `superlative:max`,
`superlative:min`. A fine intent has a template (a plan, adapted by LFM3) and may have its own handler, as in E-17d.

**How a handler is shared at the coarse level.** One handler per class, `solve(table, question, choices)`, which finds the
columns and filter values itself from the question's words and the headers and cells, so it does not depend on one
schema. (A handler that reads column "Silver" is a handler of one table.)
- It is written from 3 labelled cases of the class chosen to differ in table (distinct `table_id`) and in fine intent, and shown the class's failures on rewrite.
- It is promoted when the Wilson lower bound of its agreement with Inkling, pooled over the class's labelled cases, is at least 0.70 (9 of 9 at the least), as E-17d; and demoted on the same bound.
- A fine intent uses the class handler, unless that intent has 5 or more labels of its own and agrees on under 90% of them (E-17d's discard rule). Then the class handler is withdrawn for it (it falls to its template or Inkling), and a fine handler may be written from its own cases by the E-17d path.
- Every live candidate is observed on every new label, as E-17d.

The point of the two levels is that the 12 cases a promotion needs arrive at the coarse level (9 or 10 classes reach 9 cases
in 300 to 600 questions) and not at the fine level or the exact intent (E-17's fine intents had 17 of 35 seen once in
100 cases). By rules, 12 classes recur; the fine split gives 15 keys, 12 to 13 of them 9 or more times.

## What would make E-18 uninformative

Each of these is checked before the verdict is read, and any one of the four means the verdict is reported as "not informative", not as a pass or a fail:
1. **Too little recurrence.** Fewer than 5 classes have 9 or more cases in the first 300 by the classifier that was used (by rules, there are 9; the classifier may differ), or the ceiling on cases 301 to 450, computed by the same method from the classifier's own classes and the run's shapes, is under 40%. Then 30% cannot be told from the gate's limit.
2. **A weak reference.** Inkling's accuracy on WTQ is under 50% on the smoke test (above), so agreement with it is not a measure of correctness.
3. **Classes that are not operations.** If `lookup` and `other` together hold over 30% of cases (rules: 11% and 3%) the classes do not carve the work and the coarse level is not tested. If a class's handler is written, and agrees on its pooled labels, but with different code for each fine intent (a handler that is a switch on fine intent), the sharing claim is not tested and is reported as a class of one.
4. **Fewer cases than planned.** The stream stops before case 450 (time, a crash): the window of 150 is not measured.

## What the runner needs for WTQ

`stream.py` and `stream_v2.py` stay as they are (E-17d's registration freezes them). The runner takes WTQ cases
unchanged through `stream.load_cases(data_dir)` when the directory holds `problems_test1k.json` (tested in
`test_wtq.py`: the case has only `PROBLEM_FIELDS`, `smoke.prompt` and `stream.run_handler` work). What does not fit, and would be
a new file (for example `stream_v3.py`, importing the others, as `stream_v2.py` imports `stream.py`):

| Where | Why it does not fit | Change |
| --- | --- | --- |
| `summarize.py`: `smoke.correct(ans, gold[pid])` | reads `p["ans_type"]` and one answer; WTQ gold is a list | score with `wtq.correct`; read `problems_test1k.json` from the WTQ directory |
| `smoke.py`: `DATA`, `correct` | TabMWP path; `ans_type` | `--data`; `wtq.correct` (a copy for WTQ) |
| `stream.same` (agreement) | lists compare in order and as text; a list `Spain, Italy` and `Italy, Spain` disagree | agreement by `wtq.score` between the two answers read as WTQ items |
| `stream_v2.strict` | refuses a number list with no choices (`NUMBER_LIST`) and an answer over 100 characters; WTQ has list answers (2.6% of `test` examples have 2 or more items) | allow lists when the question asks for several (the case then goes to the large model, as now, until then) |
| `stream_v2.shape` | the exact shape is new for about half the cases at 300 | loose shape: `wtq_recurrence.coarse_shape` |
| `d1_intent.INSTRUCT`, `D1_INSTRUCTIONS` | name "a math word problem" | set from the new runner, not edited in `d1_intent.py` |
| intent levels | `stream_v2` keys intents flat | two levels, as above |
| `stream.HANDLER` prompt | examples hold the whole table as JSON | the 3 labelled cases of shortest table |
| `smoke.prompt` | the answer line says "the answer only"; a list has no form | say lists are comma-separated on one line |

WTQ's compact release has no page titles (`page/` is only in the full release), so `table_title` is None. Each table has
its header as the first line of `table`, as TabMWP's does. Duplicate or empty headers are made unique (`Year (2)`,
`col4`), because `table_for_pd` is a dictionary.

## The scorer

`wtq.correct(pred, problem)` follows the official `evaluator.py` (v1.0.2, Python 2, at the pinned commit): a target
item matches a predicted item when their normalised strings are equal (diacritics, quotes, dashes, trailing citations and
(details), outer quotes and a final period are removed; lower case), or both are numbers and equal, or both are dates and
equal. A prediction is a set, and the denotation is correct when the sizes are equal and every target item matches.
Gold comes from `tagged/data/*.tagged` (`targetValue` and CoreNLP's `targetCanon`). Differences from `smoke.correct` (tested in `test_wtq.py`):
- `smoke.correct` strips `$`, commas and units and reads the first number, so "1,000 people" and "about 3" are right for 1000 and 3. WTQ's rule is stricter: "100,000" is not a number to the official evaluator (it is only equal as a string to the raw target).
- `smoke.correct` has one answer. WTQ lists are sets, in any order, with duplicates collapsed.
- `smoke.correct` folds case only. WTQ also drops diacritics, trailing `(details)` and citations such as `[1]`.
- WTQ has dates ("1990-01-12", unknown fields `xx`) and year-only dates as numbers. A model's "January 12, 1990" does not equal the date 1990-01-12 under the official rule, only a string equal to the raw target.

One departure from the official evaluator, for model text: it takes a list of items. A model's answer is one string, so the
scorer tries it as one item first ("Paris, France"), then split on newlines, `|`, `;`, `, ` and ` and `, and counts it correct if any reading is. This can
credit a split that happens to match; it cannot credit a wrong set.
Not done: a check against the official Python 2 evaluator on a run (none was available; the port was checked by
scoring each gold answer against itself on all 4,344 `pristine-unseen-tables` examples, 0 failures, which does not test the cases that fail).
