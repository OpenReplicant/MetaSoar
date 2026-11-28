# E-20 draft: a small model takes decision types off the manager (not registered)

**Status:** a proposal for the owner, written 2026-11-28 by a cloud session. Nothing here has run. It is entered in
`docs/experiments.md` only after the owner approves it, with any changes. The ID E-19 is taken (abandoned in
development), so this is E-20.

**Source of the idea:** the handoff (`docs/handoff-2026-11-28.md`, "Next, in order", item 1): "d1-2B trained on
Haiku's manager decisions, promoted per decision type only when it agrees well enough. It runs on Kaggle and trains
on the v2 scenarios." That handoff was written by an agent session; the design text it refers to is in Substrate
(`docs/manager-agent.md`, PR #34), which this session could not read. Where this draft fills a gap, it says so.

## What are we trying to prove?

PM-1a found that no local model can be the whole manager (Inkling 69.8% routing, LFM3 20.9%, Haiku 5.5 81.4%). This
asks a narrower question: can a 2B model, trained on Haiku's own choices, make *some kinds* of routing decision as
well as Haiku does, so that Haiku is only called for the rest? If not even one kind passes, the System 1 route for
the manager (a cheap model in front, the large one at an impasse) is closed for now at this data size.

## Plain words

- **A decision** is what the manager does with one incoming message or event. It is read from the trace by PM-1a's
  `score.py`: an **action** (`answer`, `ack`, `start` a worker, `message` a worker, `stop` a worker, open a
  `decision` for the owner, `ask` the owner), the **project** it concerns, and whether it **escalated** to the owner.
- **A decision type** is the action. These are the units that are promoted.
- **Promoted** means: when d1-2B predicts that type with enough confidence, its decision is used and Haiku is not
  asked to decide. Every other case goes to Haiku, as now.
- **Teacher labels** are Haiku's decisions. **True labels** are the owner's reviewed labels on the v2 scenarios.
  d1-2B learns from Haiku (as designed); it is judged against the owner.

## Claim

On the v2 manager scenarios, d1-2B fine-tuned on Haiku 5.5's decisions is promoted for at least one decision type,
and a manager that uses d1-2B for promoted types and Haiku for the rest routes held-out scenarios as accurately as
Haiku alone.

## Out of scope

d1-2B decides only the routing. A promoted `start` still needs a worker brief, an `answer` still needs reply text,
and those would still be written by a model. So this measures whether the *decision* can leave Haiku, not the full
cost saving. The report counts, per promoted type, how many cases need no further text (only `ack`, today).

## Data and splits

1. **Labels first.** The owner reviews the 220 v2 labels (Substrate `scripts/trials/manager/scenarios-v2-review.md`).
   Blocking.
2. **Split.** `split_v2.py` (Substrate) runs after the review: train and held-out, fixed and committed before any
   model sees a scenario. Inside train, a validation fold of 20% by a hash of the scenario id. *Gap:* the split
   ratio is whatever `split_v2.py` sets; it is named here before the run.
3. **Teacher run.** Haiku 5.5 as the manager on all 220 scenarios, once each, through Substrate's harness and its
   `claude -p` driver (the Kaggle copy has no Claude driver). Decisions read by `score.py`. Haiku's routing accuracy
   against the true labels on held-out is the baseline.

## Arms

| Arm | What | In the falsifier |
| --- | --- | --- |
| H | Haiku 5.5 alone | baseline |
| D | d1-2B, LoRA on the train fold's teacher labels, read by its probabilities over the label set | yes, through the hybrid |
| H+D | D on its promoted types, H on everything else | yes |
| D0 | d1-2B untrained, same readout | reported: does training matter? |
| E | logistic regression on the Kaggle embedder's vectors, same teacher labels | reported: the cheap baseline `docs/decision-backends.md` says wins once labels exist |
| D* | as D, trained on the true labels instead of Haiku's | reported: what distilling from Haiku costs |

**Readout.** d1-2B scores each allowed answer (action, then project, then escalate) by its probability, in both
option orders, as in E-04a. The confidence of a decision is the product of the three. One input format: the
manager's prompt (`pm1a/manager.md`), the portfolio summary and the message or event.

**Training.** LoRA on the Hugging Face weights of `LiquidAI/d1-2B`, fp16, on Kaggle 2×T4. Seed 0 is the one the
gate uses; seeds 1 and 2 are reported. Hyperparameters are set on the validation fold and frozen with the runner's
commit, which is named here before the held-out run.

## The promotion gate (decided on validation, never on held-out)

For each decision type c, among validation cases where D predicts c with confidence at least τ:

1. at least 10 such cases;
2. the Wilson 95% lower bound of agreement with Haiku (action, project and escalate all equal) is at least 0.90;
3. no missed escalation: none of those cases has a Haiku or true label that escalates while D's decision does not.

τ is chosen per type on validation as the lowest value that passes 1 to 3, or the type is not promoted. Once set,
the promoted types and their τ are committed before held-out is read.

## It fails if

- no decision type is promoted; or
- on held-out, H+D's routing accuracy against the true labels is more than 2 points below H's (paired, 95%
  bootstrap interval, its upper end below −2); or
- on held-out, H+D misses 2 or more escalations that H did not miss; or
- the runner, the promoted types or τ change after their commit is named.

**Not informative** (reported instead of a pass or fail) if held-out has fewer than 50 scenarios, or the promoted
types cover fewer than 10 held-out cases.

## Reported, not in the falsifier

Per type on held-out: agreement with Haiku, accuracy against the true labels, cases taken off Haiku. d1-2B's seconds
per decision on a T4 against Haiku's. Arms D0, E and D*. Seeds 1 and 2.

## Expected weak points

- **Size.** 220 scenarios over 7 types; `stop` and `ack` were 1 and 4 of PM-1a's 43. Rare types cannot reach 10
  validation cases, so only common ones (`start`, `answer`, `decision`, `message`) can be promoted. This is a
  property of the data, and the not-informative rule covers the case where it leaves too little to measure.
- **Haiku's errors become d1-2B's.** Haiku is at 81% on PM-1a. Agreement with Haiku is the gate (the design asks for
  it); accuracy against the owner is the falsifier, so a student that copies a wrong teacher fails there.

## Needs, and owner decisions

1. The v2 label review (blocking).
2. Licences, before any training: whether Anthropic's terms allow training d1-2B on Haiku's outputs for this use, and
   whether the LFM Open License allows fine-tuning d1-2B and keeping the result. *Not yet checked.*
3. Usage: about 220 `claude -p` manager runs on Haiku for the teacher labels, and where they run (the PC, or a cloud
   session with Substrate attached).
4. Kaggle: one training job (LoRA, under an hour expected) and one scoring job, out of the 30 weekly GPU hours.
5. The gate numbers above (0.90, 10 cases, −2 points, 2 escalations) are this draft's proposal, not the owner's.

## Informs

The manager's System 1 front (M-19, M-26 applied to Substrate's manager); whether the Sonnet arm of PM-1a or more
scenarios should come first.
