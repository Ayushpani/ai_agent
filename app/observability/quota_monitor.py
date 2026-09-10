"""Free-tier quota monitor (doc §10.2). Tracks in-flight consumption per
provider so the Model Router can pre-empt failures rather than discover
a 429 mid-request.

  - Cloudflare Workers AI: 10,000 Neurons/day shared across models.
  - OpenRouter free tier: ~20 requests/minute typical; per-model quotas vary.

This is an in-memory sliding-window counter — good enough for a
single-process POC. Swap for a Redis-backed counter before running
multiple API replicas in production.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RateLimitConfig:
    max_requests: int
    window_seconds: float


@dataclass
class _ProviderState:
    config: RateLimitConfig
    timestamps: deque = field(default_factory=deque)
    daily_units_used: int = 0
    daily_reset_at: float = field(default_factory=lambda: _next_midnight_utc())


def _next_midnight_utc() -> float:
    now = time.time()
    return (now // 86400 + 1) * 86400


class QuotaMonitor:
    """Thread-safe per-provider request/unit counter with pre-emptive
    threshold checks (doc §10.3: alert at >80% of daily allowance).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: dict[str, _ProviderState] = {}
        self._daily_allowance: dict[str, int | None] = {}

    def register_provider(
        self, name: str, max_requests_per_minute: int | None = None,
        daily_unit_allowance: int | None = None,
    ) -> None:
        with self._lock:
            self._providers[name] = _ProviderState(
                config=RateLimitConfig(
                    max_requests=max_requests_per_minute or 0, window_seconds=60.0
                ),
            )
            self._daily_allowance[name] = daily_unit_allowance

    def can_call(self, provider: str, units: int = 1) -> bool:
        with self._lock:
            state = self._providers.get(provider)
            if state is None:
                return True  # unregistered provider: no local limit tracked

            now = time.time()
            if now >= state.daily_reset_at:
                state.daily_units_used = 0
                state.daily_reset_at = _next_midnight_utc()

            while state.timestamps and now - state.timestamps[0] > state.config.window_seconds:
                state.timestamps.popleft()

            if state.config.max_requests and len(state.timestamps) >= state.config.max_requests:
                return False

            allowance = self._daily_allowance.get(provider)
            if allowance is not None and state.daily_units_used + units > allowance:
                return False

            return True

    def record_call(self, provider: str, units: int = 1) -> None:
        with self._lock:
            state = self._providers.get(provider)
            if state is None:
                return
            state.timestamps.append(time.time())
            state.daily_units_used += units

    def usage_ratio(self, provider: str) -> float | None:
        """Fraction of daily allowance consumed, for the >80% alert threshold."""
        with self._lock:
            state = self._providers.get(provider)
            allowance = self._daily_allowance.get(provider)
            if state is None or not allowance:
                return None
            return state.daily_units_used / allowance


# Module-level singleton mirroring the doc's single quota-monitor process.
quota_monitor = QuotaMonitor()
quota_monitor.register_provider("cloudflare_workers_ai", daily_unit_allowance=10_000)
quota_monitor.register_provider("openrouter", max_requests_per_minute=20)
