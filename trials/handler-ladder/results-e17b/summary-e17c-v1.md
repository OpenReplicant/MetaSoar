# E-17c: answer-preserving perturbations of E-17b's cheaper-rung cases

| perturbation | variants | accuracy, original | accuracy, variant | paired difference [95% interval] | same intent | still template or handler | fallbacks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| shuffle | 111 | 91.9% | 91.9% | +0.0 [-3.6, +3.6] | 96.4% | 95.5% | 2 |
| rename | 70 | 97.1% | 88.6% | -8.6 [-15.7, -1.4] | 97.1% | 100.0% | 0 |
| paraphrase | 72 | 94.4% | 94.4% | +0.0 [+0.0, +0.0] | 88.9% | 93.1% | 0 |

Skipped (the perturbation did not apply, or a paraphrase lost a number or label): shuffle 0, rename 41, paraphrase 39

## E-17c verdict line

- refutation condition met (any perturbation's interval upper end below -3 points): NO

## Wrong on a variant, right on the original

- 37214 shuffle: compute_difference_between_counts -> compute_difference_between_counts by template, '5' (gold '8')
- 13380 rename: find_start_time -> find_start_time by template, 'intermediate ballet class' (gold 'swing dance class')
- 34178 rename: compute_remaining_money -> compute_remaining_money by template, '$76.70' (gold '542.04')
- 14537 rename: compute_remaining_money -> compute_remaining_money by template, '69,160' (gold '63,553')
- 20150 rename: compute_remaining_money -> compute_remaining_money by template, '5120' (gold '23,690')
- 30072 rename: compute_remaining_money -> compute_remaining_money by template, '50.56' (gold '66.60')
- 6681 shuffle: compute_remaining_money -> compute_remaining_money by template, '1978.41' (gold '1,522.81')
- 6681 rename: compute_remaining_money -> compute_remaining_money by template, '134.40' (gold '1,522.81')
- 3856 rename: compute_total_money_raised -> compute_total_money_raised by handler, '$15' (gold '7')
