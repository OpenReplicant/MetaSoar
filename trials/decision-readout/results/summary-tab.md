# E-04c: a tabular foundation model as the escalation gate

Gate: rank by P(Inkling right) - P(d1-2B right). Fitted on 621 `fit` cases, measured on 779 `eval` cases (Inkling alone 0.810, d1-2B alone 0.633). Differences are against the logistic gate on the same features, with 95% intervals resampling families.

| Gate | Features | 50% sent | 60% sent | 63% sent | Where gain > 0: sent, accuracy, against Inkling alone | Fit and predict s |
|---|---|---|---|---|---|---|
| logistic | F | 0.806 | 0.818 | 0.820 | 64%, 0.823, +0.013 [-0.003, +0.030] | 0.1 |
| TabICL | F | 0.793 (-0.013 [-0.028, +0.001]) | 0.810 (-0.008 [-0.022, +0.006]) | 0.813 (-0.008 [-0.020, +0.004]) | 82%, 0.823, +0.013 [+0.000, +0.027] | 11.3 |
| logistic | F + E | 0.797 | 0.815 | 0.813 | 66%, 0.813, +0.003 [-0.017, +0.020] | 0.1 |
| TabICL | F + E | 0.800 (+0.003 [-0.015, +0.020]) | 0.816 (+0.001 [-0.015, +0.018]) | 0.819 (+0.006 [-0.010, +0.023]) | 66%, 0.820, +0.010 [-0.007, +0.026] | 21.9 |
| table by type | - | 0.801 | 0.827 | 0.828 | 63%, 0.828, +0.018 [+0.003, +0.034] | 0.0 |
| confidence | - | 0.797 | 0.810 | 0.815 |  | 0.0 |

Embedding: Qwen3-Embedding-0.6B Q8_0 (revision 370f27d), 32 components explain 70% of its variance on `fit`.
TabICL 2.2.0 (checkpoint tabicl-classifier-v2-20260212, jingang/TabICL, BSD-3), scikit-learn 1.9.1, random_state 0, CPU.
