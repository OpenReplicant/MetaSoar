# Proposal: tell the handler writer about handlers_lib, and make it importable in the sandbox

Status: a proposal only. `stream.py` and `stream_v2.py` are unchanged. Per the rule for runner changes, this needs a
registered experiment (for example E-18) before anything is wired in. Nothing below has been run through the model.

## 1. The API in the HANDLER prompt

`HANDLER` in `stream.py` (line 34) says: standard library only, parse numbers defensively. Proposed addition, placed
before "Reply at once":

```
Helpers are already defined in your code's namespace, with no import; use them rather than writing your own:
num(cell) -> float or None (strips $ , % and units; "1/2", "2 1/2" are fractions; times give None)
numeric_columns(table) -> names of the all-numeric columns, in order
label_column(table) -> name of the first non-numeric column (the row labels)
is_stem_leaf(table) -> True for a Stem / Leaf table (names and cells decide, not the question)
stem_leaf_values(table) -> every value of a stem-and-leaf table as a whole number (stem 2, leaf 1 -> 21)
parse_time(s) -> minutes after midnight for "11:15 A.M." or "2.10 P.M." (None if not a time)
match_choice(answer, choices) -> the choice that equals answer (text or number), as written, or None
row_by_label(table, text) -> index of the row whose label appears in text (plurals allowed), or None
threshold(question) -> a test v -> bool for "at least 40", "less than 5" etc., or None
```

The listing is the whole prompt change. Each line is one function with a docstring in `handlers_lib.py`, so the
writer can read the detail when it needs it. Expected effect, to be measured: shorter handlers (the 32 distinct stored
handlers total 1,749 lines, about 55 each), and fewer stem-and-leaf and label-lookup mistakes.

## 2. Making it importable in the sandbox

Today `run_handler` (stream.py line 187) writes `handler.py` and `harness.py` into a temp directory and runs
`python3 -I harness.py`. The harness then `exec`s the handler in a namespace that pre-imports `re`, `math`,
`statistics`, `fractions`, `datetime` and `collections`. Under `-I` the script's directory is not on `sys.path`, and
the reply is prefilled from `def solve`, so the writer cannot add top-level imports. The change has three parts:

1. `run_handler` copies `handlers_lib.py` into the temp directory next to `handler.py`. The file is read-only input,
   the same as `handler.py`, and the rlimits still apply.
2. In `HARNESS`, before the `exec`, add the directory to the path and inject the public names:

```python
sys.path.insert(0, os.getcwd())
import handlers_lib as _lib
ns.update({k: getattr(_lib, k) for k in _lib.__all__})
```

3. `__all__` in `handlers_lib.py` (already there) is the single list of names to inject. A name added to the library
   reaches the prompt and the sandbox only when it is added to `__all__` and to the listing in section 1.

Injecting the names, rather than asking the writer to `from handlers_lib import ...`, keeps the prefill working and
keeps the reply to one code block.

## 3. Things to check in the experiment

- Versions. A stored handler that calls `num` depends on the library as it was when the handler was written. Pin
  the library version in the run's record (a hash of `handlers_lib.py`), and re-run the stored handlers against a
  changed library before promoting it.
- Shadowing. The injected names come before `exec`, so a handler that defines its own `num` overrides the library. Count
  how often this happens; it is a sign the listing is not read.
- Baseline. Run the current prompt and the new prompt on the same cases, and compare handler length, the
  handler-written rate, its accuracy against gold, and the cost of writing one handler (45 to 120 s now).
- Stem-and-leaf. Both the old and the new prompt should be scored on stem-and-leaf intents specifically, since that
  is where the original failures were.

## 4. What the tests already show

`test_handlers_lib.py` runs five handlers rewritten on the library (`handlers_rewritten.py`) against the original
code in `results/state.json`. All five give the same answers as the original on the constructed cases. Two
(`find_maximum_count` and `count_people_interviewed_no`) differ on stem-and-leaf tables, where the original was wrong
and the rewrite gives the right answer. See `results/handler-patterns.md` for the counts.
