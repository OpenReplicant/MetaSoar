# E-17c: answer-preserving perturbations of E-17b's cheaper-rung cases

| perturbation | variants | accuracy, original | accuracy, variant | paired difference [95% interval] | same intent | still template or handler | fallbacks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| shuffle | 111 | 91.9% | 91.9% | +0.0 [-3.6, +3.6] | 96.4% | 95.5% | 2 |
| rename | 37 | 94.6% | 94.6% | +0.0 [+0.0, +0.0] | 97.3% | 94.6% | 1 |
| paraphrase | 72 | 94.4% | 94.4% | +0.0 [+0.0, +0.0] | 88.9% | 93.1% | 0 |

Skipped (the perturbation did not apply, or a paraphrase lost a number or label): shuffle 0, rename 74, paraphrase 39

## E-17c verdict line

- refutation condition met (any perturbation's interval upper end below -3 points): NO

## Wrong on a variant, right on the original

- 37214 shuffle: compute_difference_between_counts -> compute_difference_between_counts by template, '5' (gold '8')
- 6681 shuffle: compute_remaining_money -> compute_remaining_money by template, '1978.41' (gold '1,522.81')
