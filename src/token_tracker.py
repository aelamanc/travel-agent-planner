"""Token/latency bookkeeping shared by every strategy and agent.

Replaces the ad hoc `start_time = time.time()` / `total_tokens += ...`
duplicated across every strategy before the Anthropic migration. Anthropic's
`usage` object splits input/output tokens with no combined field, so this is
tracked as two numbers throughout, not one.
"""

import sys
import time
from dataclasses import dataclass


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __iadd__(self, other: "TokenUsage") -> "TokenUsage":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        return self

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class StrategyRunTracker:
    """Accumulates token usage and elapsed time across one strategy.run() call."""

    def __init__(self):
        self.usage = TokenUsage()
        self._start = time.monotonic()

    def record(self, loop_result) -> None:
        """Fold a llm_loop.LoopResult's usage into this run's total."""
        self.usage += loop_result.usage

    @property
    def latency_seconds(self) -> float:
        return time.monotonic() - self._start


class RunSpendTracker:
    """Cumulative input/output token counter across an eval run, printed to stdout."""

    def __init__(self):
        self.usage = TokenUsage()

    def add(self, usage: TokenUsage) -> None:
        self.usage += usage
        print(
            f"[spend] cumulative input={self.usage.input_tokens} "
            f"output={self.usage.output_tokens} total={self.usage.total}",
            file=sys.stdout,
        )
