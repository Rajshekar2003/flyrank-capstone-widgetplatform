"""Abuse protection: per-IP and per-widget sliding-window rate limits, client IP, honeypot."""
import ipaddress
import time
from collections import deque

from fastapi import Request

from app import config
from app.errors import TooManyRequests

HONEYPOT_FIELD = "website"


class SlidingWindowLimiter:
    """Allows at most max_requests per window_seconds for each key (IP or widget id)."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window = window_seconds
        self.hits: dict[str, deque] = {}

    def check(self, key: str) -> float:
        """Record a hit. Returns 0 if allowed, otherwise seconds until a slot frees up."""
        now = time.monotonic()
        if len(self.hits) > 10_000:
            self._purge(now)
        timestamps = self.hits.setdefault(key, deque())
        while timestamps and now - timestamps[0] >= self.window:
            timestamps.popleft()
        if len(timestamps) >= self.max_requests:
            return self.window - (now - timestamps[0])
        timestamps.append(now)
        return 0.0

    def _purge(self, now: float) -> None:
        stale = [k for k, ts in self.hits.items() if not ts or now - ts[-1] >= self.window]
        for k in stale:
            del self.hits[k]


IP_LIMITER = SlidingWindowLimiter(config.RATE_LIMIT_IP_MAX, config.RATE_LIMIT_IP_WINDOW_SECONDS)
WIDGET_LIMITER = SlidingWindowLimiter(config.RATE_LIMIT_WIDGET_MAX, config.RATE_LIMIT_WIDGET_WINDOW_SECONDS)


def get_client_ip(request: Request) -> str:
    """The address of the real client.

    Without TRUST_PROXY this is the socket peer. With it, the client is the Nth entry counted
    from the RIGHT of X-Forwarded-For, where N is TRUSTED_PROXY_HOPS: each of our own proxies
    appends the address it saw, so entries further left were supplied by the client (or by
    untrusted hops) and can be forged. If the chain is shorter than expected, the request did
    not come through our proxies, so the socket peer is used.
    """
    if config.TRUST_PROXY:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= config.TRUSTED_PROXY_HOPS:
            try:
                return str(ipaddress.ip_address(parts[-config.TRUSTED_PROXY_HOPS]))
            except ValueError:
                pass
    return request.client.host if request.client else "unknown"


def too_many_requests(retry_after: float, scope: str):
    seconds = max(1, int(retry_after) + 1)
    raise TooManyRequests(
        f"Too many requests ({scope} limit). Try again in {seconds}s.",
        headers={"Retry-After": str(seconds)},
    )


def is_honeypot_filled(data: dict) -> bool:
    value = data.get(HONEYPOT_FIELD)
    if isinstance(value, str):
        return value.strip() != ""
    return value is not None
