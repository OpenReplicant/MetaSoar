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
./run_d1.sh > results/run-d1.log 2>&1                           # d1 models, then score them the same way
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

**Inkling 2 Mini, 100 families per slice** (1,400 cases, 2,800 reads, no errors; `results/summary-inkling.md`).
Pooled on the `eval` half (779 cases):

| System | Accuracy [95% CI] | Brier | Calibration error | Coverage at 5% risk (realised risk) |
| --- | --- | --- | --- | --- |
| Inkling, raw | 0.787 [0.752, 0.820] | 0.343 | 0.129 | 0.43 (0.054) |
| Inkling, debiased | 0.810 [0.775, 0.843] | 0.302 | 0.091 | 0.56 (0.073) |
| Inkling, debiased and scaled | 0.810 [0.775, 0.843] | 0.283 | 0.051 | 0.51 (0.043) |
| Jev 1.13 | 0.843 [0.813, 0.873] | 0.236 | 0.032 | 0.64 (0.058) |
| djev 0.1 | 0.661 [0.627, 0.703] | 0.506 | 0.205 | 0.18 (0.057) |
| Laya 421M | 0.452 [0.412, 0.492] | 0.664 | 0.151 | 0.06 (0.062) |

- **E-04a's falsifier is not met for Inkling.** It is 3.3 points below Jev (paired, families resampled: 95% interval
  [-6.5, -0.3] points), so the gap is real but small. Its coverage at 5% risk is 0.51 against Jev's 0.64.
- **Case by case:** both right on 583 cases, only Inkling on 48, only Jev on 74.
- **Inkling is ahead on:**
  - ATBench: 0.97 against 0.92.
  - Prompt injections: 0.90 against 0.75.
  - PubMedQA: 0.75 against 0.67.
  - ScienceQA: 0.98 against 0.95.
- **Inkling is level on:** jailbreak (0.98 each), MedQA (0.84 against 0.85) and MedMCQA (0.80 against 0.82).
- **Inkling is behind on:** MMLU-Pro (0.55 against 0.78) and the Aegis slices (0.75 against 0.89, and 0.67 against 0.80).
- **Order effects are much smaller than LFM3's:** a flip rate of 0.15 against 0.33.
- **Fits the published pattern.** Inkling is a mixture of experts with about 26B parameters in all, the size at
  which the decision-gate study found likelihood readouts matching Jev (Gemma-4-31B, Qwen3.6-27B). LFM3 at 1.7B does
  not reach it untuned.
- **Cost of the result:** speed. Inkling takes 2.3 s per read (median) with its experts split between the GPU and RAM,
  and 25 s on ATBench's long trajectories. LFM3 takes 0.11 s.
- **Caveat:** a sample of 100 families per slice, half of them held out. Every slice is in it.

**Liquid's open d1 models: every usable case** (`results/summary-d1.md`).
- **Setup:** their own GGUFs at Q8_0 (Hugging Face revisions: d1-2B `4a18109`, d1-omni-600M `8eb2d2a`), on
  llama.cpp's native `/v1/systemone` endpoint (`readout_d1.py`). The JevBench question is sent as it is, in both
  option orders; 13,032 reads each, no errors.
- **d1-3B is not run:** Liquid has deprecated it, saying d1-2B is more accurate with a third fewer parameters.

Pooled on the `eval` half (3,412 cases):

| System | Accuracy [95% CI] | Brier | Calibration error (as shipped / scaled) | Coverage at 5% risk | Order-flip rate | ms per read |
| --- | --- | --- | --- | --- | --- | --- |
| d1-2B | 0.640 [0.619, 0.660] | 0.461 | 0.037 / 0.016 | 0.33 | 0.09 | 77 |
| d1-omni-600M | 0.457 [0.438, 0.476] | 0.683 | 0.188 / 0.028 | 0.01 | 0.20 | 23 |
| LFM3 1.7B, our readout | 0.501 raw, 0.528 debiased | 0.764 | 0.311 / 0.026 | 0.09 | 0.33 | 108 |
| Jev 1.13 | 0.842 [0.828, 0.857] | 0.229 | 0.024 | 0.67 | - | - |

On the same 779 held-out cases as Inkling's sample:

| System | Accuracy |
| --- | --- |
| Inkling (debiased) | 0.810 |
| d1-2B (debiased) | 0.633 |
| LFM3 (debiased) | 0.561 |
| d1-omni-600M (debiased) | 0.481 |
| Jev 1.13 | 0.843 |

- **E-04a's falsifier is met for both d1 models:** d1-2B is 20 points below Jev, and d1-omni-600M 38 points below.
- **What d1-2B's training buys over the general model at its size** (LFM3, read by us):
  - 11 points of accuracy;
  - calibration as shipped close to Jev's (0.037);
  - order-stable answers (no flips at all on yes or no questions);
  - 77 ms per read.
- **Where d1-2B is close to Jev:**
  - PubMedQA: 0.70 against 0.72.
  - Prompt injections: 0.72 against 0.74.
  - Aegis: 0.81 against 0.85, and 0.77 against 0.80.
  - Jailbreak: 0.95 against 0.99.
- **Where it is far behind:**
  - Knowledge: MedQA 0.50 against 0.86, MedMCQA 0.42 against 0.76, MMLU-Pro 0.40 against 0.79. Its own card warns
    that knowledge-heavy questions favour larger models.
  - ATBench's long agent trajectories: 0.64 against 0.92.
- **Reading so far:**
  - Inkling read by its probabilities is the only local backend near Jev's accuracy, at 2.3 s a decision.
  - d1-2B is the fast, calibrated, stable one, good where the answer is in the text.
  - That suggests a cascade: d1-2B first, and Inkling when d1-2B is unsure or the question needs knowledge. This
    is the decision-gate study's rule: a cheap first stage that is confident where it is right.

**The cascade: d1-2B first, Inkling when unsure** (`cascade.py`, `results/summary-cascade.md`). Offline, on the
1,400 cases both models read; choices on `fit`, measured on `eval` (779 cases). Both models are read debiased, so
a decision costs two reads of each model it reaches; cost is the measured time of those reads.

| Policy | Accuracy | Sent to Inkling | Mean s per decision |
| --- | --- | --- | --- |
| d1-2B alone | 0.633 | 0% | 0.30 |
| Inkling alone | 0.810 | 100% | 9.42 |
| Escalate below d1-2B's confidence t (t chosen on `fit`) | 0.769 | 38% | 3.44 |
| Knowledge slices straight to Inkling, d1-2B elsewhere | 0.810 | 58% | 7.16 |
| Escalate exactly where d1-2B is wrong (oracle) | 0.865 | 37% | 4.53 |

- **A threshold trades accuracy for cost:** a third of Inkling's time for 4 points less (-4.1 [-6.6, -1.6]).
- **The models' errors differ:** d1-2B is better than Inkling on Aegis (0.82 against 0.75, and 0.83 against 0.67
  on responses), so the oracle passes Jev's 0.843. d1-2B's confidence finds only part of that gap.

**E-04b: a learned front** (`learned_front.py`, `results/summary-front.md`). A logistic model predicts "d1-2B is
wrong" from what is known before escalating (its probabilities in both orders, margin, entropy, order flip,
number of options, prompt length; and, in a second front, the question's type). Trained on `fit` of all 6,516
cases d1-2B read.
- **Falsifier met:** the fronts are no better than d1-2B's own confidence. AUROC for its errors is 0.817 for all
  three; the cascade's accuracy at 30%, 40% and 50% sent differs by at most half a point, every interval across 0.
- **Why:** d1-2B is calibrated, so its confidence already says how likely it is to be wrong; more features of its
  own output add nothing (entropy carries the weight, the order features are near zero since it rarely flips).
- **What does help (exploratory, not registered):** ranking by what escalation gains, P(Inkling right | type) on
  `fit` minus d1-2B's confidence, not by what d1-2B gets wrong. Escalating where that is positive sends 63% to
  Inkling and beats Inkling alone: 0.828, +1.8 [+0.3, +3.4]. At 60% sent it beats the confidence by +1.7
  [+0.8, +2.8].
- **Reading:** a gate should model the gain, so it needs the second stage's record, not only the first stage's
  output. Information the first stage does not have (the question's type here; embeddings or nearest cases next)
  is where a learned gate can add anything. Caveat: the type is the benchmark's slice; in use it would be the
  kind of question asked, which a typed question has.

**E-04c: a tabular foundation model as the gate** (`embed.py`, `front_tab.py`, `results/summary-tab.md`). The
gate ranks by P(Inkling right) - P(d1-2B right), each from a model fitted on the 621 `fit` cases both read.
- **Learners:** logistic regression (scikit-learn), and TabICL 2.2.0 (BSD-3; checkpoint
  `tabicl-classifier-v2-20260212`), in-context, untuned, on the CPU.
- **Features:** E-04b's plus the question's type; then, as well, 32 principal components of an embedding of the
  question (Qwen3-Embedding-0.6B Q8_0, Apache-2.0, Qwen's own GGUF at `370f27d`; `serve.sh embed`; 3.5 minutes for
  1,400 questions on the GTX 1070).
- **Environment:** numpy, scikit-learn and tabicl are not in the system Python; a `uv venv` with them, torch for
  the CPU. TabICL's checkpoint downloads from Hugging Face on first use.

| Gate | Features | 60% sent | Where expected gain > 0: sent, accuracy, against Inkling alone [95% CI] |
| --- | --- | --- | --- |
| logistic | outputs + type | 0.818 | 64%, 0.823, +1.3 [-0.3, +3.0] |
| TabICL | outputs + type | 0.810 | 82%, 0.823, +1.3 [0.0, +2.7] |
| logistic | + embedding | 0.815 | 66%, 0.813, +0.3 [-1.7, +2.0] |
| TabICL | + embedding | 0.816 | 66%, 0.820, +1.0 [-0.7, +2.6] |
| Inkling's record by type (E-04b) | type | 0.827 | 63%, 0.828, +1.8 [+0.3, +3.4] |

- **Falsifier met:** TabICL is not above logistic regression on the same features at any rate (every interval
  crosses 0; on outputs and type it is 0.8 to 1.3 points lower).
- **The embedding adds nothing** for either learner, and costs the logistic gate a point.
- **The best gate is the simplest:** Inkling's `fit` record per question type, minus d1-2B's confidence.
- **Reading:** with 621 labelled cases, what predicts the gain is the kind of question and d1-2B's confidence. A
  richer learner or a richer description of the question fits noise. The embedding mostly restates the type,
  which is one-hot already. Whether finer signals pay needs far more cases with both outcomes, which is what an
  online gate collects (E-04d).
