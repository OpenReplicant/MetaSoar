"""Tier 2 wire models: the action adds measured seconds; the observation adds the clock and the scores."""
from __future__ import annotations

from typing import Any, Dict, Optional

from openenv.core.env_server.types import State

from .models import ManagerAction, ManagerObservation


class DayAction(ManagerAction):
    """ManagerAction plus `seconds` (end_turn only): the turn's measured wall seconds. Without it the environment
    measures them itself (from the arrival's delivery to this end_turn), which is not deterministic; tests and replays
    pass it. A tool call may carry metadata["t"], the seconds into the turn at which it was made; without it a call is
    placed at the end of the turn when `seconds` is given, else at its measured time."""

    seconds: Optional[float] = None


class DayObservation(ManagerObservation):
    """One arrival for a fresh manager session (message, tools), or a tool result inside the turn. `scenario_id` is the
    arrival's id. After end_turn the observation is the next arrival's, with `arrival_score` the finished arrival's
    score dict and `reward` its routing (1.0 or 0.0). On the last one `done` is true, `episode` holds the day's metrics
    and `reward` is the mean per-arrival routing (the episode terms are reported, not weighted)."""

    day_id: str = ""
    arrival_index: int = 0
    source: str = ""
    kind: str = ""
    clock_s: float = 0.0
    clock: str = "09:00"
    queue_len: int = 0
    arrival_score: Optional[Dict[str, Any]] = None
    arrival_record: Optional[Dict[str, Any]] = None
    episode: Optional[Dict[str, Any]] = None


class DayState(State):
    day_id: str = ""
    arrival_id: str = ""
    clock_s: float = 0.0
    done: bool = False
