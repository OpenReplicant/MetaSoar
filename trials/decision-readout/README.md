# E-04a: local models read as decision models, against Jev

`docs/experiments.md` E-04a; the reasoning is in `docs/decision-backends.md`.

**Cases:** the Leanmcp JevBench release, pinned at revision `ed50fe0`. Each case has a state, a typed question
(`choice` or `noul`) with its options, and a gold answer; the release also ships Jev 1.13's, djev 0.1's and Laya's
probabilities for every case. Ten slices are used. SST-5 is left out because its sentence text is withheld, and
BANKING77 is left out for now because of its 77 options. Fetch the data into `../data/jevbench-ed50fe0/` (it is not
committed; each case keeps its source's licence):

```sh
B=https://huggingface.co/datasets/Leanmcp/jevbench/resolve/ed50fe0381714d1c0273cbe03cece755b25d586b
D=../data/jevbench-ed50fe0
for f in aegis2 aegis2_response atbench500 jailbreak_classification medmcqa medqa_usmle mmlu_pro prompt_injections pubmedqa scienceqa_text; do
  curl -sfL --create-dirs -o $D/cases/$f.jsonl $B/cases/$f.jsonl; done
for s in jev-1.13.0 djev-0.1 laya-421m-en; do for f in meta.json predictions.jsonl scores.json; do
  curl -sfL --create-dirs -o $D/predictions/$s/$f $B/predictions/$s/$f; done; done
```

**The readout (`readout.py`):**
- **Prompt:** the question's instructions, the state as JSON and the options labelled A, B, C..., ending "Reply
  with the letter of one option only".
- **Generation:** `Answer:` is prefilled as the start of the model's reply, thinking is off, one token is generated
  and its top 50 log-probabilities are kept. The option letters' probabilities are renormalised. An option outside
  the top 50 gets half the smallest probability listed.
- **Two reads per case:** options in the case's order and reversed.

**Serving (`serve.sh`):** Substrate's pinned llama.cpp image `server-cuda12-b12627` and model files (Substrate S-169),
on localhost only.
- `fast` is LFM3 1.7B Q6_K, wholly on the GPU, with thinking off by `enable_thinking: false`.
- `slow` is Inkling 2 Mini Q4_K, with the experts of loop layers 6–12 on the GPU, with thinking off by
  `reasoning_effort: none`.

`run.sh` runs both in turn, one on the GPU at a time.

**Scoring (`score.py`):**
- **Split:** families are split by a hash into `fit` and `eval`. Each temperature and each 5%-risk threshold is
  chosen on `fit`; everything reported is measured on `eval`.
- **Our models, three ways:** raw (the case's order), debiased (the mean of both orders) and scaled (debiased, plus
  one temperature per slice).
- **References:** Jev, djev and Laya, as shipped, on the same cases.
- **Measures:** accuracy with a 95% interval from resampling families, Brier score, calibration error, coverage at
  5% risk with its realised risk, order-flip rate, letter mass (the share of probability on option letters) and
  milliseconds per read.

```sh
./run.sh > results/run.log 2>&1
python3 -I score.py results/lfm3.jsonl results/inkling.jsonl   # writes results/summary.md
```

## Results so far (2026-11-25)

**LFM3 1.7B, every usable case** (6,516 cases, 13,032 reads, no errors; `results/summary-lfm3.md`). Pooled over ten
slices, on the `eval` half (3,412 cases):

| System | Accuracy [95% CI] | Brier | Calibration error | Coverage at 5% risk (realised risk) |
| --- | --- | --- | --- | --- |
| LFM3, raw | 0.501 [0.481, 0.521] | 0.764 | 0.311 | 0.03 (0.034) |
| LFM3, debiased | 0.528 [0.508, 0.547] | 0.699 | 0.227 | 0.03 (0.112) |
| LFM3, debiased and scaled | 0.528 [0.508, 0.547] | 0.553 | 0.026 | 0.09 (0.072) |
| Jev 1.13 | 0.842 [0.828, 0.857] | 0.229 | 0.024 | 0.67 (0.050) |
| djev 0.1 | 0.669 [0.650, 0.688] | 0.500 | 0.194 | 0.18 (0.075) |
| Laya 421M | 0.409 [0.392, 0.429] | 0.717 | 0.184 | 0.05 (0.088) |

- **E-04a's falsifier is met for LFM3 read untuned:** 31 points below Jev, and a seventh of its coverage.
- **Calibration is not the gap; accuracy is.** One temperature per slice brings the calibration error to Jev's level.
- **Close to Jev where the answer is in the text:**
  - Aegis 2.0 prompts and responses: 0.76 against 0.85 and 0.80.
  - Prompt injections: 0.78 against 0.74; the intervals overlap.
- **Far below where knowledge or reasoning is needed:** MedQA 0.43 against 0.86, MedMCQA 0.41 against 0.76, MMLU-Pro
  0.35 against 0.79. JEVal saw the same pattern for one-pass readouts.
- **Three slices show behaviour, not noise:**
  - **PubMedQA:** it answers "maybe" about 94% of the time, in either option order (0.23 accuracy, below chance).
  - **ATBench:** it calls nearly every agent trajectory unsafe (0.47, chance).
  - **MMLU-Pro:** its first token is " The" or " We" about 58% of the time, so the read is not its answer there.
    Only half its probability is on letters, and its order-flip rate is 0.67.
- **Prompt engineering to try first:** the template, a one-line example, and a stronger answer-first instruction.
  These are the cell's `change` (`docs/decision-backends.md`).
- **Fine-tuning:** self-distillation, as SII-Decision and Tacit do, if the template is not enough.
- **Speed:** 108 ms per read (median) on the GTX 1070.

**Inkling 2 Mini:** running, on 100 families per slice.
