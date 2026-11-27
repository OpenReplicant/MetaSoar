# E-04b: a learned front for the cascade

Trained on the `fit` half of d1-2B's reads (3104 cases), measured on `eval` (3412 cases; d1-2B wrong on 36%).

| Score | AUROC for d1-2B's errors on `eval` | on `fit` |
|---|---|---|
| d1-2B confidence | 0.817 | 0.828 |
| front, outputs only | 0.817 | 0.828 |
| front, + type | 0.817 | 0.829 |

The cascade on the 779 `eval` cases Inkling read (Inkling alone 0.810, d1-2B alone 0.633). The top share by each score goes to Inkling.

| Sent to Inkling | Score | Accuracy | Against the confidence [95% CI] | Mean s per decision |
|---|---|---|---|---|
| 30% | d1-2B confidence | 0.743 |  | 2.11 |
| 30% | front, outputs only | 0.738 | -0.005 [-0.014, +0.003] | 2.01 |
| 30% | front, + type | 0.738 | -0.005 [-0.016, +0.005] | 2.00 |
| 30% | oracle | 0.836 | +0.092 [+0.069, +0.117] | 4.01 |
| 40% | d1-2B confidence | 0.777 |  | 3.78 |
| 40% | front, outputs only | 0.775 | -0.001 [-0.010, +0.006] | 3.71 |
| 40% | front, + type | 0.773 | -0.004 [-0.013, +0.004] | 3.65 |
| 40% | oracle | 0.858 | +0.081 [+0.059, +0.104] | 4.65 |
| 50% | d1-2B confidence | 0.797 |  | 5.57 |
| 50% | front, outputs only | 0.802 | +0.005 [-0.001, +0.013] | 5.55 |
| 50% | front, + type | 0.801 | +0.004 [-0.004, +0.012] | 5.13 |
| 50% | oracle | 0.832 | +0.035 [+0.013, +0.058] | 6.21 |

Exploratory (not registered): ranked by expected gain, P(Inkling right | type) from `fit` minus d1-2B's confidence.

| Sent to Inkling | By confidence | By expected gain | Against the confidence [95% CI] |
|---|---|---|---|
| 30% | 0.743 | 0.743 | +0.000 [-0.014, +0.014] |
| 40% | 0.777 | 0.787 | +0.010 [-0.003, +0.024] |
| 50% | 0.797 | 0.801 | +0.004 [-0.006, +0.014] |
| 60% | 0.810 | 0.827 | +0.017 [+0.008, +0.028] |
| 63% (where expected gain > 0) | | 0.828 | against Inkling alone +0.018 [+0.003, +0.034] |
