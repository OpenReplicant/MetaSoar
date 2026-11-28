"""The reward: score.score, unchanged, on the finished episode; 1.0 if routing_ok else 0.0."""
from __future__ import annotations

from openenv.core.rubrics import Rubric

from . import _pm1a  # noqa: F401
import score as S  # noqa: E402

from . import refs  # noqa: E402


class RoutingRubric(Rubric):
    """Reads the episode from the environment it is attached to (scenario, fresh portfolio, trace, result) and calls
    score.score once the observation says done. `last_detail` keeps the whole score dict for the observation's metadata."""

    def __init__(self, env):
        super().__init__()
        object.__setattr__(self, "_env", env)
        object.__setattr__(self, "last_detail", None)

    def forward(self, action, observation) -> float:
        ep = self._env.episode
        if ep is None or not observation.done:
            return 0.0
        detail = S.score(ep["scenario"], ep["portfolio"], ep["trace"], ep["res"])
        if self._env.options.get("project_refs"):  # off by default: the score is then score.score's, as in parity.py
            detail = refs.rescore(detail, ep["scenario"], ep["stub"].p, ep["trace"], ep["content"])
        object.__setattr__(self, "last_detail", detail)
        return 1.0 if detail["routing_ok"] else 0.0
