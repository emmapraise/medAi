import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, Response, status

from app.config import settings


def get_client_ip(request: Request) -> str:
    """
    Extracts the client IP address from the incoming request.
    Handles proxies via X-Forwarded-For and X-Real-IP headers.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Entries to the left of the trusted proxies are client-supplied and
        # spoofable, so count from the right.
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[max(len(hops) - max(settings.TRUSTED_PROXY_COUNT, 1), 0)]
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host
    
    return "unknown_client"


class InMemorySlidingWindowLimiter:
    """
    Thread-safe in-memory rate limiter using a sliding window algorithm.
    Tracks timestamps per key and automatically purges expired entries.
    """

    def __init__(self, cleanup_interval_seconds: int = 300):
        self._lock = threading.Lock()
        self._records: dict[str, deque[float]] = defaultdict(deque)
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = cleanup_interval_seconds

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, int, int, int]:
        """
        Evaluates whether a request with the given key is allowed under the rate limit.

        Returns:
            (allowed, remaining, reset_timestamp_epoch, retry_after_seconds)
        """
        now = time.monotonic()
        current_time_epoch = time.time()
        window_start = now - window_seconds

        with self._lock:
            # Periodic cleanup of stale keys
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup_stale_keys(now)
                self._last_cleanup = now

            timestamps = self._records[key]

            # Pop entries outside of sliding window
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) < max_requests:
                # Request is permitted
                timestamps.append(now)
                remaining = max_requests - len(timestamps)
                oldest = timestamps[0] if timestamps else now
                reset_in = max(1, int(window_seconds - (now - oldest)))
                reset_epoch = int(current_time_epoch + reset_in)
                return True, remaining, reset_epoch, 0
            else:
                # Rate limit exceeded
                oldest = timestamps[0]
                retry_after = max(1, int(window_seconds - (now - oldest)))
                reset_epoch = int(current_time_epoch + retry_after)
                return False, 0, reset_epoch, retry_after

    def _cleanup_stale_keys(self, current_mono: float, max_idle: float = 600.0) -> None:
        """Removes keys that have no activity within the idle period."""
        stale_keys = []
        for k, timestamps in self._records.items():
            while timestamps and timestamps[0] <= (current_mono - max_idle):
                timestamps.popleft()
            if not timestamps:
                stale_keys.append(k)
        for k in stale_keys:
            self._records.pop(k, None)

    def reset(self) -> None:
        """Clears all stored rate limit history (useful for testing)."""
        with self._lock:
            self._records.clear()

    def get_stats(self) -> dict:
        """Returns diagnostic statistics about current tracked keys."""
        with self._lock:
            return {
                "tracked_keys_count": len(self._records),
                "total_recorded_requests": sum(len(q) for q in self._records.values())
            }


# Global in-memory limiter instance
limiter_store = InMemorySlidingWindowLimiter()


class RateLimiter:
    """
    FastAPI dependency for applying route-level in-memory rate limits.

    Example:
        @router.post("/ask", dependencies=[Depends(RateLimiter(times=5, seconds=60))])
        def ask(...):
    """

    def __init__(
        self,
        times: int = 60,
        seconds: int = 60,
        namespace: str | None = None,
        key_func: Callable[[Request], str] | None = None,
        enabled: bool = True
    ):
        self.times = times
        self.seconds = seconds
        self.namespace = namespace
        self.key_func = key_func or get_client_ip
        self.enabled = enabled

    def __call__(self, request: Request, response: Response) -> None:
        if not self.enabled:
            return

        client_key = self.key_func(request)
        route_path = self.namespace or request.url.path
        storage_key = f"{route_path}:{client_key}"

        allowed, remaining, reset_epoch, retry_after = limiter_store.is_allowed(
            key=storage_key,
            max_requests=self.times,
            window_seconds=self.seconds
        )

        # Attach standard rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.times)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_epoch)

        if not allowed:
            response.headers["Retry-After"] = str(retry_after)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "detail": f"Too many requests. Limit is {self.times} per {self.seconds}s. Try again in {retry_after} seconds.",
                    "retry_after": retry_after
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.times),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_epoch)
                }
            )
