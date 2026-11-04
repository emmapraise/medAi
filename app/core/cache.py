import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any


class InMemoryCache:
    """
    Thread-safe In-Memory LRU (Least Recently Used) cache with TTL (Time-To-Live) expiration.
    Guarantees bounded memory consumption and microsecond lookup latency without Redis.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600, name: str = "default"):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.name = name
        self._cache: OrderedDict[str, tuple[Any, float, float]] = OrderedDict()  # key -> (value, expire_at, created_at)
        self._lock = threading.Lock()
        
        # Telemetry metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Any | None:
        """
        Retrieves a cached value if it exists and has not expired.
        Updates LRU order upon access.
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expire_at, _ = self._cache[key]
            now = time.time()

            if expire_at is not None and now > expire_at:
                # Expired - remove and record miss
                del self._cache[key]
                self._misses += 1
                return None

            # Mark as recently used
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Sets a key-value pair in cache with an optional TTL (in seconds).
        Evicts the oldest entry if max_size limit is reached.
        """
        effective_ttl = ttl if ttl is not None else self.default_ttl
        expire_at = (time.time() + effective_ttl) if effective_ttl > 0 else None
        created_at = time.time()

        with self._lock:
            if key in self._cache:
                self._cache[key] = (value, expire_at, created_at)
                self._cache.move_to_end(key)
                return

            # Check capacity and evict LRU entry if full
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
                self._evictions += 1

            self._cache[key] = (value, expire_at, created_at)

    def delete(self, key: str) -> bool:
        """Deletes a single key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clears all entries in this cache."""
        with self._lock:
            self._cache.clear()

    def reset_stats(self) -> None:
        """Zeroes hit/miss/eviction counters (used for test isolation)."""
        with self._lock:
            self._hits = self._misses = self._evictions = 0

    def get_stats(self) -> dict:
        """Returns cache telemetry and performance statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_ratio = round((self._hits / total_requests * 100), 2) if total_requests > 0 else 0.0
            
            # Count currently active (non-expired) items
            now = time.time()
            active_count = sum(1 for _, expire_at, _ in self._cache.values() if expire_at is None or expire_at > now)

            return {
                "name": self.name,
                "current_size": active_count,
                "max_size": self.max_size,
                "default_ttl_seconds": self.default_ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio_percent": hit_ratio,
                "evictions": self._evictions,
            }


def generate_cache_key(*args: Any, **kwargs: Any) -> str:
    """
    Generates a deterministic SHA256 hex string cache key from arbitrary arguments.
    """
    normalized_dict = {
        "args": [str(a).strip().lower() if isinstance(a, str) else a for a in args],
        "kwargs": {
            k: (str(v).strip().lower() if isinstance(v, str) else v)
            for k, v in sorted(kwargs.items())
        }
    }
    encoded = json.dumps(normalized_dict, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# Dedicated In-Memory Cache Instances
qa_cache = InMemoryCache(max_size=1000, default_ttl=3600, name="qa_cache")
search_cache = InMemoryCache(max_size=2000, default_ttl=1800, name="search_cache")
analytics_cache = InMemoryCache(max_size=20, default_ttl=30, name="analytics_cache")


def get_all_cache_stats() -> dict:
    """Aggregates performance statistics from all active in-memory cache stores."""
    return {
        "qa_cache": qa_cache.get_stats(),
        "search_cache": search_cache.get_stats(),
        "analytics_cache": analytics_cache.get_stats(),
    }


def clear_all_caches() -> None:
    """Flushes all in-memory caches (e.g. on new dataset ingestion or admin reset)."""
    qa_cache.clear()
    search_cache.clear()
    analytics_cache.clear()
