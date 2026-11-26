# E-17: the handler ladder on TabMWP

Registered in `docs/experiments.md` (E-17); design in `docs/handler-ladder.md`. A stream of 300 `test1k` cases
(sorted ids, `random.Random(17)` shuffle, first 300), in chunks of 100, measured on the last 150.

## Run

```
python3 -I -m unittest                    # fake models, no servers
python3 -I stream.py --chunk 1            # then 2, then 3; resumes exactly; refuses if the previous chunk is incomplete
python3 -I baseline.py                    # large model alone on last-150 cases a cheaper rung answered (resumable)
python3 -I summarize.py                   # writes results/summary-e17.md
```
Flags (all three scripts): `--large-url/--large-model` (default `http://127.0.0.1:8081`, `slow`), `--small-url/--small-model`
(`http://127.0.0.1:8082`, `fast`), `--data`, `--out`, `--n`, `--chunk-size`. Output: `results/state.json` (the truth),
`results/stream.jsonl` (rewritten from the state after each case), `results/baseline.jsonl`.

## Serving

The large model (Inkling, `slow`, `reasoning_effort: none`) is on :8081. The small model (LFM3, `fast`,
`enable_thinking: false`) is on :8082. They do not fit on the 8 GB GPU together, so the small model may run on the CPU
(the runner assumes nothing about where either lives; it only speaks HTTP and keeps per-model call, token and second
counts, so a CPU small model shows up as small-model seconds). The small model may reason in its text, so the
`Intent:` and `Answer:` lines are parsed from the end.

## Design

- Gold (`answer`, `ans_type`, `ques_type`, `solution`) is never loaded by the runner: `load_cases` copies a whitelist of
  fields. Only `summarize.py` reads gold. A test runs the stream on data with altered gold and expects an identical run.
- A policy is promoted on agreement with the large model's own answers (labels), never gold. Held-out means labelled
  cases the candidate was not written from; a candidate also shadows each later large-model-answered case.
- Candidates: one handler and one template per intent, each rewritten at most once (versions v1, v2). A discarded or
  uncompilable candidate is not recompiled.
- Handlers run in `python3 -I` in a temp dir with `resource` limits and sockets disabled. This is a guard against
  accidents, not a security sandbox.
- A fallback case (the chosen rung failed its check) is recorded as rung `large`, `fallback: true`, and counts as a
  large-model case (so it is a label and is not "covered").
- Agreement and the stream's own checks use one normaliser: numbers as numbers, a bare number equals number plus unit
  words, other text case-folded; with choices, the answer is mapped onto its choice.
- There is no demotion yet (E-07): an active policy that later fails only falls back, case by case.

**Reviewed before the first run (2026-11-26):**
- **Shadow starvation, fixed.** A candidate learns only from the large model's labels. Once a template was promoted,
  the handler (cheaper) got none and could never be promoted. Now, while a handler is in shadow, the large model also
  labels the cases the template answers (`shadow_label` in `stream.jsonl`; its calls count in the case's cost). This
  stops once the handler is promoted or discarded. A test covers it.
- **Known weak points, kept:** a handler written from exactly 3 labels has no held-out cases at birth, so its
  promotion rests on its next 3 labelled cases (3 of 3); there is no demotion (a promoted policy that goes bad
  falls back case by case); the TabMWP file holds gold beside the questions, so gold is in memory while cases load,
  but no runner object carries it (tested).
- **Fixed after 13 real cases (the run was stopped and restarted from the start, its record kept in
  `results/aborted-2026-11-26/`):** LFM3's reasoning leaked into intent keys (`..._think_intent_che`), so the key is
  now the first answer line after `Intent:`, cut at `<`, "end with" or a hedge (" or "), at most 4 words. Inkling
  reasoned for its whole budget on handler prompts and wrote no code, so its reply is prefilled with
  `def solve(...)`, which gives code at once. The harness pre-imports `re`, `math`, `statistics`, `fractions`,
  `datetime` and `collections`. Answers that both hold numbers agree when the numbers do and neither answer's words
  contradict the other's (`-34 kg per year` and `-34 kg/year` agree; `March 3` and `April 3` do not). A write that
  returns nothing usable is retried once on a later label.
- **Serving:** `serve.sh ladder`. Inkling has loop layers 6-11 on the GPU, and LFM3 is on the GPU with its KV cache
  in RAM. Inkling runs at 13.6 tok/s, against 14.5 with 8 layers, and an intent call takes 0.41 s, against 3.0 s
  with LFM3 on the CPU.
