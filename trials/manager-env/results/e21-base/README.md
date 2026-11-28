# E-21 train-day baseline (Kaggle `e21-train-base2`, commit 36aebe7)

`manager.md`, no env options; Inkling `prefill auto`, LFM3 thinking off; 2x T4. Inkling ran train-00..04 (time), LFM3 all
ten. The rollouts (`*.rollouts`, 16 MB) are kept out of git, in `trials/kaggle/runs/e21-train-base2/`.

| Model | Days | Routing (pooled over arrivals) | Per day |
| --- | --- | --- | --- |
| Inkling | 5 | 92/135 = 0.68 | 0.92, 0.50, 0.71, 0.54, 0.60 |
| LFM3 | 10 | 261/574 = 0.45 | 0.33 to 0.56 |

- Owner wait: Inkling median about 45 s (train-00: 136 s, p90 618 s); LFM3 about 3 s.
- LFM3 days train-03, -08 and -09 ran to 124-133 arrivals (the scripted days have 19-39): it starts workers in loops
  (88 starts on train-03, up to 9 in one turn), and each started worker sends its own events. Its dropped loops (32-38) and
  double writers (up to 39) on those days come from that. Pooled routing over-weights those days; per-day means are
  reported too. The one-call router (`stop_after_action`) stops this by construction.
- In-sample note: this is the train side of E-21; candidates are chosen here and judged once on held-out days.
