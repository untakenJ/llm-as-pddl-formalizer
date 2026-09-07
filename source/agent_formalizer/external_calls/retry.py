"""Small recovery state machine shared by streaming models and external tools."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Callable


class Action(str, Enum):
    RETURN = "return"
    INVALIDATE = "invalidate"
    RETRY = "retry"


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    exhausted: Action = Action.INVALIDATE
    replay: str = "same_request"


class ExternalCallInvalid(RuntimeError):
    """Caller must invalidate generation, or leave evaluation unresolved."""

    def __init__(self, reason: str, *, diagnostic: str = "", evidence=None):
        super().__init__(reason)
        self.reason = reason
        self.diagnostic = diagnostic
        self.evidence = evidence or {}


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int
    backoff_seconds: tuple[float, ...]
    max_retry_after_seconds: float = 60.0
    recovery_timeout_seconds: float | None = None

    def __post_init__(self):
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        if not self.backoff_seconds or any(not math.isfinite(x) or x < 0 for x in self.backoff_seconds):
            raise ValueError("backoff_seconds must contain finite non-negative delays")
        if not math.isfinite(self.max_retry_after_seconds) or self.max_retry_after_seconds < 0:
            raise ValueError("invalid Retry-After bound")
        if self.recovery_timeout_seconds is not None and (
            not math.isfinite(self.recovery_timeout_seconds) or self.recovery_timeout_seconds <= 0
        ):
            raise ValueError("recovery timeout must be positive and finite")

    def delay(self, retry_index: int, headers=None, *, now: float | None = None) -> float:
        raw = headers.get("Retry-After") if headers is not None else None
        parsed = None
        if raw:
            try:
                parsed = float(raw)
            except (TypeError, ValueError):
                try:
                    parsed = parsedate_to_datetime(raw).timestamp() - (time.time() if now is None else now)
                except (TypeError, ValueError, OverflowError):
                    pass
        if parsed is not None:
            return round(max(0.0, min(self.max_retry_after_seconds, parsed)), 6)
        return self.backoff_seconds[min(retry_index, len(self.backoff_seconds) - 1)]


class RetryController:
    """Owns bounded retry decisions; the API adapter owns IO and replay safety.

    Reuse one controller across nested transport/operation recovery so counts
    cannot multiply. Streaming callers can use this without buffering a stream.
    """

    def __init__(self, policy: RetryPolicy, *, monotonic: Callable[[], float] = time.monotonic):
        self.policy = policy
        self.monotonic = monotonic
        self.retries = 0
        self.recovery_started: float | None = None

    def remaining(self) -> float | None:
        if self.recovery_started is None or self.policy.recovery_timeout_seconds is None:
            return None
        return max(0.0, self.policy.recovery_timeout_seconds - (self.monotonic() - self.recovery_started))

    def decide(self, decision: Decision, *, replay_safe: bool = True, headers=None) -> tuple[Action, float]:
        if decision.action != Action.RETRY:
            return decision.action, 0.0
        if not replay_safe:
            return Action.INVALIDATE, 0.0
        if self.recovery_started is None:
            self.recovery_started = self.monotonic()
        delay = self.policy.delay(self.retries, headers)
        remaining = self.remaining()
        if self.retries >= self.policy.max_retries or (remaining is not None and remaining <= delay):
            return decision.exhausted, 0.0
        self.retries += 1
        return Action.RETRY, delay

    @staticmethod
    def wait(seconds: float, *, cancelled: Callable[[], bool] = lambda: False,
             sleep: Callable[[float], None] = time.sleep) -> None:
        # Bounded chunks let callers stop without waiting for a long backoff.
        while seconds > 0:
            if cancelled():
                raise ExternalCallInvalid("external_call_cancelled")
            chunk = min(seconds, 0.1)
            sleep(chunk)
            seconds -= chunk
