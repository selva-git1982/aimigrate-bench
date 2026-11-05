"""Bounded retries for transient Gemini API failures."""
from __future__ import annotations
import random
import time
from typing import Callable, TypeVar

T = TypeVar('T')


def is_retryable(exc: Exception) -> bool:
    """Retry only explicit HTTP 429/500/502/503/504 errors."""
    code = getattr(exc, 'code', None)
    if code is None:
        code = getattr(exc, 'status_code', None)
    if code is None:
        match = __import__('re').search(r'\b(429|500|502|503|504)\b', str(exc))
        code = int(match.group(1)) if match else None
    try:
        return int(code) in {429, 500, 502, 503, 504}
    except (TypeError, ValueError):
        return False


def call_with_retries(
    operation: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
    sleep: Callable[[float], None] = time.sleep,
    on_attempt: Callable[[], None] | None = None,
) -> T:
    """Attempt operation at most max_attempts times, including initial call.

    on_attempt runs immediately before every attempt, allowing the caller to
    enforce a global request budget. Failed attempts still count.
    """
    if max_attempts < 1:
        raise ValueError('max_attempts must be >= 1')
    for attempt in range(max_attempts):
        if on_attempt is not None:
            on_attempt()
        try:
            return operation()
        except Exception as exc:
            if attempt + 1 >= max_attempts or not is_retryable(exc):
                raise
            delay = min(max_delay, base_delay * (2 ** attempt))
            sleep(delay)
    raise AssertionError('unreachable')
