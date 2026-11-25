# Decision backends: what the evidence supports before we pick one

A research note, 2026-11-25, following `docs/typed-questions.md`. The owner asked whether we are jumping the gun on
decision models: whether a small model we run ourselves can be expected to match published results, and whether the
other System 1 methods in the cascade (`docs/system1-skills.md`, "A cascade, by cost") should be tried first.

**Short answer.** The typed-question interface (M-22) is well supported. The backend is not decided by the evidence,
and our own model sits below every size anyone has published a likelihood readout for. Two cheaper families have
stronger evidence for our two uses: classifiers on embeddings where labels exist, and the answering model's own
agreement or confidence for when to think. So E-04 should compare those before it trusts a typed question put to the
1.7B, and a cheap check on JevBench should come first.

## What was measured elsewhere

**Decision gates, one harness for every model class** (arXiv 2610.00346 v2; section 6 and the conclusion read in
full, the tables partly). Eight decision-model checkpoints, four open generative models served by vLLM (Qwen3-14B
AWQ 4-bit, Qwen3.6-27B FP8, Gemma-4-31B and Mistral-Small-24B in bf16), trained classifiers and a zero-shot NLI model,
all given the same requests.

- **When labels exist, a trained classifier wins.** A fine-tuned DeBERTa-v3-large (under 0.5B) had the highest
  accuracy on every labelled task except one: 0.953 on CLINC-150 against Jev's 0.913. Logistic regression on
  BGE-small embeddings reached 0.948 on CLINC-150 and 0.702 on the workflow decisions (Jev 0.732).
- **Without labels, it depends on the checkpoint, not on the class.** Gemma-4-31B and Qwen3.6-27B read by the
  likelihood of each option key matched Jev; Qwen3-14B and Mistral-Small-24B stayed significantly below it. No
  generative model under 14B was tested.
- **Read the key's likelihood, not stated probabilities.** One model's stated probabilities could not be parsed in
  0.767 of its emotion replies.
- **Raw probabilities are miscalibrated, and one temperature per task fixes most of it.** Gemma-4-31B's key
  likelihoods: calibration error 0.244 as shipped, 0.064 after one temperature fitted on held-out data. A temperature
  fitted under one option count does not carry to another (Kev-9B: 0.051 to 0.377 at 150 options).
- **Order effects are large for untrained readers.** Swapping yes and no flipped at least 16.8 answers per hundred for
  every generative model, against at most 6.5 for fine-tuned decision checkpoints (and 50.5 for Jev).
- **Thresholds belong to one model on one task,** set on held-out labels and checked on more: the same Jev accepts 0.93
  of intent decisions but 0.17 of workflow decisions at 5% risk.
- **Cascades pay when the cheap stage knows the task's labels;** an untrained first stage gained only where both
  stages were weak.

**JEVal** (arXiv 2610.03935 v2, abstract, experiments and sections 6 to 9 read). 11,257 items from 36 datasets, 25
configurations, open models served by vLLM on H100s.

- Qwen3.5-4B, generating without thinking: accuracy 61.4, calibration error 0.253; with thinking: 70.7, 0.172. Jev:
  78.4, 0.053.
- An open model's first-token readout is a decision model (their Finding 11), and distilling its own post-reasoning
  answer into that readout (SII-Decision-4B, -27B) brings the 27B to Jev's level in about 0.1 s.
- Distillation recovers most of what thinking adds on label selection (intent, harm, emotion), but **a quarter or less
  on reasoning-heavy sets** (GPQA, MMLU-Pro): one pass does not reproduce multi-step computation.
- Decision models choose the likeliest option but overstate its probability, and weaken where specialist knowledge or
  long context is needed.

**When to think** (three papers):

- **DART** (arXiv 2606.23181 v4, results read): training-free. Sample two cheap no-think drafts; if they agree, answer
  directly; if not, think, with a budget from the drafts' entropy. On Qwen3 8B to 32B and DeepSeek-V3.2 it matched or
  beat always-thinking on 13 of 14 model and benchmark pairs while cutting thinking tokens by 32 to 73%, and its
  first-stage signal held from 0.6B to 32B. On Qwen3-8B, **asking the model whether it needs to think** (MC-Binary)
  matched on MATH-500 (85.8) but collapsed on HumanEval (10.4, against 78.7 for DART); supervised MLP and boosted-tree
  routers on draft features did worse than DART on maths.
- **Zero-shot confidence for small LLMs** (arXiv 2605.02241 v3; 7 to 8B models, MMLU-Pro and TriviaQA): the mean
  log-probability of the model's own answer predicted correctness with AUROC 0.65 to 0.71, better than asking it
  whether it was confident (0.56 to 0.64). A RouteLLM-style logistic regression on query embeddings, trained on 1,000
  labels, was close in distribution (0.66 to 0.68) but fell to 0.546 on the other dataset.
- **Learning When to Think** (arXiv 2608.20256 v2, abstract read): a 1.5B model trained with GRPO to pick NoThink,
  Short or Long as its first token kept MATH500 accuracy (0.782 against 0.796) at 41% fewer tokens. It needs training,
  so it is a later option, not a baseline.

**Quantisation.** Mixed and thin: one study found 4-bit GPTQ lowered confidence on correct answers most where the
model was already unsure; another found the effect on calibration generally minor; a clinical study saw logit-based
calibration error rise from 0.15 to 0.26 at 4 bits. None tested llama.cpp's K-quants. Our 1.7B is Q6_K and Inkling
Q4_K: measure, do not assume.

## What that means for us

| Claim we rely on | Evidence | Status |
| --- | --- | --- |
| An LLM's first-token readout gives typed decisions | JEVal Finding 11; the gates paper | supported |
| A 1.7B read that way is good enough | none published under 4B; 4B already far below Jev uncalibrated | **unsupported: measure** |
| Debiasing and one temperature per task make it usable | the gates paper (temperature), PriDe and AnyJev (order) | supported for larger models |
| Asking a model "should this be processed with thinking?" works | DART's MC-Binary: fine on maths, collapsed on code | **weak** |
| The answering model's own agreement or confidence predicts when thinking helps | DART (0.6B to 32B), Nguyen (7 to 8B) | supported |
| Embedding classifiers are strong once labels exist | the gates paper (logistic regression on BGE-small) | supported, but brittle out of distribution (Nguyen) |
| Readout replaces thinking on reasoning-heavy questions | JEVal: a quarter of the gain or less | **no**: this is why when-to-think matters |

So we are not early on the interface, which every result fits. We would be early to name the 1.7B the backend, and to
make E-04's main observer a typed question about thinking, which is the observer with the weakest evidence.

## Proposed order

1. **E-04a, a readout check on JevBench (new, cheap).** The Leanmcp cases (pinned at `ed50fe0`) ship Jev 1.13's,
   djev's and Laya's own probabilities. Read LFM3 1.7B and Inkling on the same cases (one forward pass each, no
   thinking): raw, debiased (both orders, a label prior) and with one temperature per slice fitted on half. Report
   accuracy, Brier, calibration error, order-flip rate and coverage at 5% risk, against Jev on the same items. This
   answers "can we expect comparable results with our own models" in hours, not days, and checks the readout
   against generated answers on a sample (`docs/typed-questions.md`).
2. **E-04 with the observers reordered by evidence:** always on and always off; the slow model's own confidence in its
   direct answer (the margin of the readout from step 1, which costs nothing extra); draft agreement (DART's first
   stage: two short no-think drafts); logistic regression and nearest neighbours on embeddings, with local labels;
   the typed question to the 1.7B and to Inkling last. Separate slices in and out of the training distribution,
   since that is where embedding routers failed.
3. **Only then choose a backend for M-22,** per task, with its readout level and temperature recorded (M-21's
   calibration). Self-distillation (SII-Decision's recipe, AnyJev's Tacit) is the later route if a small readout is
   close but not enough.

## Sources

- [Benchmarking System One decision models against trained classifiers and language models for automated decision gates](https://arxiv.org/html/2610.00346v2)
- [General Decision Models: Benchmarking and Insights Beyond Jev](https://arxiv.org/pdf/2610.03935) (JEVal; data at `carlosxiang/JEVal` on Hugging Face)
- [DART: Draft-Agreement Routing for Training-Free Adaptive Thinking Budgets](https://arxiv.org/pdf/2606.23181) (code: `js-lee-AI/DART` on GitHub)
- [Zero-Shot Confidence Estimation for Small LLMs](https://arxiv.org/html/2605.02241)
- [Learning When to Think: Adaptive Reasoning for Test-Time Compute Allocation](https://arxiv.org/pdf/2608.20256)
- [When Quantization Affects Confidence of Large Language Models?](https://arxiv.org/pdf/2405.00632) (NAACL Findings 2024)
- [Uncertainty-Aware Calibrated Clinical Text Classification with Large Language Models](https://arxiv.org/pdf/2509.19375)
- [Leanmcp/jevbench](https://huggingface.co/datasets/Leanmcp/jevbench) (cases with gold answers and three systems' predictions)
