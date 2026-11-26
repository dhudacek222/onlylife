"""The AI seams (BRIEF.md §2.2). Implementations get only per-observer data and return plain data;
they never import engine.world / engine.db / engine.rules (enforced by tests/test_harness.py)."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Decision:
    actions: list  # list[engine.actions.Action]; [] = not understood
    confidence: float  # calibrated: below Config.escalate_below the harness escalates or asks
    source: str = "rules"  # rules | llm
    injection: bool = False  # tried to talk to the system instead of acting in the world
    suggestions: list = field(default_factory=list)  # likely commands to offer as buttons when not understood
    usage: dict | None = None  # {"model", "input_tokens", "output_tokens", "cache_read_input_tokens", "latency_ms"}


class DecisionModel(Protocol):
    def decide(self, text: str, view: dict) -> Decision:
        """text -> ordered structured actions. `view` is Engine.view(actor): only what the actor perceives."""


class Narrator(Protocol):
    def narrate(self, facts: dict) -> str:
        """One observer's facts (built from that observer's perception row only) -> text for that observer."""
