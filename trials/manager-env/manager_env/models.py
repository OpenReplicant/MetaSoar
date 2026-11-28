"""The environment's action and observation types (OpenEnv wire models)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field


class ManagerAction(Action):
    """One manager move: a tool call, or the end of the turn.

    type "call_tool":  tool_name and arguments (one of stub_pm.TOOLS; any other name counts as an attempt outside the set).
    type "end_turn":   text is the closing text of the turn (the reply to a person's message); empty keeps the last text
                       sent with a tool call (metadata["content"]).
    type "list_tools": returns the tool list and costs no step.
    metadata may carry "content" (text sent alongside a tool call), "tokens" (drivers.tokens()-shaped usage) and "error"
    (a failure to put in the score).
    """

    type: Literal["call_tool", "end_turn", "list_tools"] = "call_tool"
    tool_name: str = ""
    arguments: Dict[str, Any] = Field(default_factory=dict)
    text: str = ""


class ManagerObservation(Observation):
    """What the manager sees. `message` and `tools` come with reset; `tool_result` with each call. On the last step done is
    true, reward is 1.0 or 0.0, and metadata["score"] is score.score's whole dict."""

    scenario_id: str = ""
    message: str = Field(default="", description="the incoming message or event (score.message_for)")
    tools: List[Dict[str, Any]] = Field(default_factory=list, description="stub_pm.TOOLS (on reset and list_tools)")
    tool_result: Optional[str] = None
    tool_error: bool = False
    nudge: Optional[str] = Field(default=None, description="set when one step is left and the final_nudge option is on")
    step: int = 0
    max_steps: int = 10
    score: Optional[Dict[str, Any]] = Field(default=None, description="score.score's dict, on the last step (also in metadata, which the HTTP wire drops)")


class ManagerState(State):
    scenario_id: str = ""
    done: bool = False
