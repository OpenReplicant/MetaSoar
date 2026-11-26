# Typed questions: how a language model is used in place of a Jev-style decision model

A research note for M-22, 2026-11-25. The question: how is an ordinary language model made to answer typed
questions (a choice, a yes or no, a score) with probabilities, as TypeSafe's Jev does, and what is known about
doing it well? The owner's own finding is the starting point: a 1.7B local model read by its token probabilities
"outperformed the jev-clones on the few questions we tested".

## The contract being replaced

Jev (TypeSafe, 2026-09-15) takes a state (text or JSON) and typed questions, and returns, for each question, a
probability for every allowed answer, in one pass, with nothing generated. Its claim of no hallucination is about
format: it cannot answer outside the schema, but it can answer wrongly. That contract is M-22's `builtin: ask`.

## Three ways to meet it with an open model

| Way | How | Examples (November 2026) |
| --- | --- | --- |
| **Read a plain model** (no training) | prompt with the state, the question and labelled options; take the next-token distribution; keep only the options' tokens; softmax over them | the owner's 1.7B; AnyJev's training-free `Decider` (any causal model, on transformers, vLLM, SGLang or llama.cpp); SemIf (options' logits from a frozen Qwen3.5-4B) |
| **Train a decision model** | replace or supplement the text head: a linear head over option codes, one pass per option framed as entailment, or an encoder | Karpo Decision 31B (a head scoring 255 option codes on Gemma 4 31B); openjev-4B v5 (one pass per option, NLI framing); Laya (a 421M ModernBERT encoder); Mammoth-1 (a Brier term in the loss, an explicit "I don't know") |
| **Self-distil, then escalate** | train the model to give in one pass the answer it reaches when it reasons; when the top two options are close, re-run with reasoning | AnyJev's Tacit, 1.7B to 9B; escalation when the log-probability gap is under a threshold, capped at a share of recent decisions |

The third is M-19's System 1 and System 2 inside one model: a fast read, an impasse when it is not confident, and
deliberation with a budget. It arrived at the same shape independently.

On the community leaderboards, open models now rank above the proprietary reference. On Decision Index 0.4.1 (a
Hugging Face leaderboard, mostly private test sets), Jev 1.14 is 67th with 60.24, below 66 other
entries; Karpo Decision 31B is first with 73.86. On JevBench's public items, openjev-4B v5 scores 0.814 against
Jev 1.13's 0.866, with the gap on the hard tier (0.622 against 0.730). Most of these numbers are self-reported or
single runs, without intervals.

## Reading a plain model: the engineering

**The prompt.** The state, then the question, then the options with short labels (`A`, `B` or `yes`, `no`), then the
answer position. For a chat model, put the answer position in the assistant's turn (prefill `Answer:`) so the next
token is the answer and not a preamble. For a reasoning model, turn thinking off in the chat template, or the first
token is the start of a thought.

**Check that the read is the answer.** An instruction-tuned model's first-token probabilities can disagree with the
answer it would write: Wang et al. (ACL Findings 2024) found mismatch above 60% for Llama-2-7B-Chat, and it
persisted when the prompt forced an option letter first. So on a sample, compare the read with the generated
answer before trusting the read.

**Options of more than one token.** Either label each option with one token and read the label, or score each
option's whole text. Scoring the text needs a normalisation: the sum of log-probabilities favours short options;
dividing by token length (SGLang's default) or by byte length (lm-eval's option) corrects that, each with its own
failure (a long option whose later tokens are near certain once it starts). Dividing by the option's probability
without the state removes surface-form competition, where paraphrases of the right answer split its probability
(Holtzman et al., EMNLP 2021, PMI_DC).

**Engines.**

| Engine | What it gives |
| --- | --- |
| Hugging Face transformers | the full logits of every position; anything can be computed |
| vLLM | `logprobs` and `prompt_logprobs` per token; `allowed_token_ids` keeps only the given tokens' scores; `logit_bias` |
| SGLang | `select` with a `choices_method`: token-length normalised (the default), greedy first token, or normalised by unconditional likelihood |
| llama.cpp server | `n_probs` returns the top tokens' probabilities at each step; `post_sampling_probs` returns them after the sampling chain |

**Many questions, one state.** Put the state first so the engine's prefix cache holds it, and each question is a short
suffix. Several questions then cost little more than one. A trained head that branches per question (Karpo) does
the same inside the model.

## Biases and how they are removed

| Bias | What it is | Fix, and what it needs |
| --- | --- | --- |
| **Label (token) bias** | the model puts more mass on some option labels (`A`, `C`) whatever they say | PriDe (Zheng et al., ICLR 2024): estimate the prior over labels by permuting options on a few states (about 5%), divide it out; no labels needed |
| **Position bias** | options at some positions are favoured | read once per rotation of the options and average (AnyJev's L0); or score each option on its own, so order affects only the normalisation (openjev v5: shuffling changed no labels on 231 items) |
| **Contextual bias** | the prompt's format and examples push towards some answers | contextual calibration (Zhao et al., ICML 2021): read the model on a content-free input such as "N/A" and fit a correction that makes it uniform; batch calibration (Zhou et al., 2023) estimates the bias from a batch of real inputs instead |
| **Surface-form competition** | paraphrases of an answer share its probability | PMI_DC, as above |
| **Overconfidence after preference tuning** | RLHF generally worsens the calibration of log-probabilities (Tian et al., EMNLP 2023, on Llama-70B) | fit a temperature or a monotone map on cases with known outcomes; verbalised confidence was better calibrated for several large chat models, but it costs generation |

AnyJev's numbers show how much the free fixes buy. On Qwen3-8B, BANKING77 with 20 classes, 300 items, raw readout
against L0 (rotations plus a label prior, no labels): order-flip rate 0.230 to 0.073, accuracy 0.747 to 0.803,
expected calibration error 0.240 to 0.184, and the share of decisions confident enough to automate at no more than
5% error from 7.7% to 46.3%. One model, one task, one run.

Size helps calibration: Kadavath et al. (2022) found large models well calibrated on multiple-choice and true/false
questions in the right format, improving with size and few-shot examples. A 1.7B model is far below the sizes
studied, so its probabilities should be assumed miscalibrated until measured, and corrected by the runner (M-21).

## The risk: the state is untrusted

The state a typed question reads is often a tool's output, a web page or a message: text an adversary may write.
openjev-4B v5's own card reports that one adversarial line cut its accuracy on 150 JevBench items from 0.833 to
0.467, and it recommends pairing it with deterministic checks. So M-21's rule holds with force: a typed question
over untrusted state may drive `inject` and `route`; a policy that acts (`run` with a `reversible` or `irreversible`
effect) needs a deterministic condition as well, from `core/` or its own skill.

## What this means for M-22

1. **The backend declares its readout level,** as AnyJev's decisions do: `raw`, `debiased` (permutation or rotation
   with a label prior), `calibrated` (fitted on outcomes). The runner records it with every case, and a policy may
   require a level.
2. **Adopt coverage at fixed risk as the measure of a System 1 matcher:** the share of states it may take while its
   errors stay under a bound. It is the number that says how much model work System 1 removes, and it moves with
   both accuracy and calibration.
3. **Experiment 5's protocol, made concrete.** Backends: the owner's 1.7B read raw and debiased; AnyJev's
   Tacit-1.7B (the same size, self-distilled); a small trained decider (decider-2B or Laya); Jev as the reference.
   For each: accuracy, Brier score and expected calibration error, order-flip rate, coverage at 5% risk, and
   milliseconds per decision, on held-out benchmark questions and then on real inputs. Check the read against
   generated answers on a sample. Each with and without the nearest cases in the state.
4. **Escalation is an impasse.** Tacit's rule (a small gap between the top two options sends the decision to
   reasoning, capped at a share) is M-22's tie, with a budget. The cap is a setting for Morphogen to tune, like the
   audit rate.

## Open questions

- Does the owner's result hold beyond a few questions, and is it accuracy or calibration that wins?
- How far does a debiased 1.7B read fall behind a trained decider of the same size on coverage at fixed risk?
- Are retrieved cases in the state worth their tokens, or does a tabular model over features do better at the same
  cost?
- How much does a typed question's wording move its answers (Artificial Analysis now measures this as symmetry under
  rewording), and should wording be a tuned parameter?

## Sources

- TypeSafe's Jev: [DataCamp's overview](https://www.datacamp.com/blog/system-one-models-jev),
  [Sanity's glossary entry](https://www.sanity.io/glossary/jev-typesafe-ai-model)
- [AnyJev](https://github.com/nokia-applied-research/AnyJev) (training-free decider, L0, Tacit)
- [openjev](https://huggingface.co/AlexWortega/openjev), [Open Jev collection](https://huggingface.co/collections/Ferr0/open-jev-typed-decision-models),
  [open data collection](https://huggingface.co/collections/davanstrien/jev-style-decision-models-open-data)
- [Pinggy: seven self-hosted decision models](https://pinggy.io/blog/best_open_source_jev_alternatives_self_hosted_decision_models/)
  (Decision Index 0.4.1, Artificial Analysis Decision Index v2)
- Wang et al., ["My Answer is C"](https://arxiv.org/abs/2402.14499) (ACL Findings 2024)
- Zheng et al., [Large Language Models Are Not Robust Multiple Choice Selectors](https://arxiv.org/abs/2309.03882) (ICLR 2024)
- Zhao et al., [Calibrate Before Use](https://arxiv.org/abs/2102.09690) (ICML 2021); Zhou et al., [Batch Calibration](https://arxiv.org/abs/2309.17249)
- Holtzman et al., [Surface Form Competition](https://arxiv.org/abs/2104.08315) (EMNLP 2021)
- Tian et al., [Just Ask for Calibration](https://arxiv.org/abs/2305.14975) (EMNLP 2023)
- Kadavath et al., [Language Models (Mostly) Know What They Know](https://arxiv.org/abs/2207.05221) (2022)
- Biderman et al., [Lessons from the Trenches on Reproducible Evaluation](https://arxiv.org/abs/2405.14782) (normalisations in lm-eval)
- Engines: [SGLang choices methods](https://docs.sglang.ai/frontend/choices_methods.html),
  [vLLM sampling parameters](https://docs.vllm.ai/en/latest/api/vllm/sampling_params/), llama.cpp server's `n_probs`
  and `post_sampling_probs`
