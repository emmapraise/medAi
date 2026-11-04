import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.cache import (
    InMemoryCache,
    analytics_cache,
    clear_all_caches,
    generate_cache_key,
    get_all_cache_stats,
    qa_cache,
    search_cache,
)
from app.core.rate_limiter import InMemorySlidingWindowLimiter, RateLimiter, get_client_ip

ADMIN = {"X-API-Key": "test-admin-key"}


def test_in_memory_sliding_window_limiter():
    """Tests core rate limiter sliding window logic, allowed vs blocked requests, and remaining counts."""
    limiter = InMemorySlidingWindowLimiter()
    key = "test_user_1"
    max_requests = 3
    window = 2  # 2 seconds

    # 1st request -> allowed, 2 remaining
    allowed, remaining, reset_epoch, retry_after = limiter.is_allowed(key, max_requests, window)
    assert allowed is True
    assert remaining == 2
    assert retry_after == 0

    # 2nd request -> allowed, 1 remaining
    allowed, remaining, reset_epoch, retry_after = limiter.is_allowed(key, max_requests, window)
    assert allowed is True
    assert remaining == 1

    # 3rd request -> allowed, 0 remaining
    allowed, remaining, reset_epoch, retry_after = limiter.is_allowed(key, max_requests, window)
    assert allowed is True
    assert remaining == 0

    # 4th request -> blocked!
    allowed, remaining, reset_epoch, retry_after = limiter.is_allowed(key, max_requests, window)
    assert allowed is False
    assert remaining == 0
    assert retry_after >= 1

    # Another user is not affected
    allowed_other, rem_other, _, _ = limiter.is_allowed("test_user_2", max_requests, window)
    assert allowed_other is True
    assert rem_other == 2

    # Wait for window to expire
    time.sleep(2.1)
    allowed_after, rem_after, _, _ = limiter.is_allowed(key, max_requests, window)
    assert allowed_after is True
    assert rem_after == 2


def test_fastapi_rate_limiter_dependency():
    """Tests the RateLimiter dependency in a FastAPI test app with headers and 429 response."""
    test_app = FastAPI()
    limiter = RateLimiter(times=2, seconds=60, namespace="test_route")

    @test_app.get("/limited", dependencies=[Depends(limiter)])
    def limited_endpoint():
        return {"status": "ok"}

    client = TestClient(test_app)

    # 1st request -> 200 OK
    res1 = client.get("/limited", headers={"X-Forwarded-For": "192.168.1.10"})
    assert res1.status_code == 200
    assert res1.headers["X-RateLimit-Limit"] == "2"
    assert res1.headers["X-RateLimit-Remaining"] == "1"

    # 2nd request -> 200 OK
    res2 = client.get("/limited", headers={"X-Forwarded-For": "192.168.1.10"})
    assert res2.status_code == 200
    assert res2.headers["X-RateLimit-Remaining"] == "0"

    # 3rd request -> 429 Too Many Requests
    res3 = client.get("/limited", headers={"X-Forwarded-For": "192.168.1.10"})
    assert res3.status_code == 429
    assert "Retry-After" in res3.headers
    assert res3.headers["X-RateLimit-Remaining"] == "0"
    data = res3.json()
    assert "Rate limit exceeded" in data["detail"]["error"]

    # Different IP should succeed
    res_diff = client.get("/limited", headers={"X-Forwarded-For": "192.168.1.99"})
    assert res_diff.status_code == 200
    assert res_diff.headers["X-RateLimit-Remaining"] == "1"


def test_in_memory_lru_and_ttl_cache():
    """Tests cache get/set, TTL expiration, and LRU max capacity eviction."""
    cache = InMemoryCache(max_size=3, default_ttl=1, name="test_cache")

    # Set 3 items
    cache.set("a", 100)
    cache.set("b", 200)
    cache.set("c", 300)

    assert cache.get("a") == 100
    assert cache.get("b") == 200
    assert cache.get("c") == 300

    # Access "a" so "b" becomes least recently used
    _ = cache.get("a")

    # Add 4th item -> should evict "b" (since "a" and "c" were accessed more recently)
    cache.set("d", 400)
    assert cache.get("b") is None  # Evicted
    assert cache.get("a") == 100
    assert cache.get("c") == 300
    assert cache.get("d") == 400

    stats = cache.get_stats()
    assert stats["evictions"] == 1
    assert stats["hits"] >= 4

    # Test TTL Expiration
    time.sleep(1.1)
    assert cache.get("a") is None
    assert cache.get("d") is None


def test_deterministic_cache_key_generation():
    """Tests that deterministic SHA256 cache keys are stable and whitespace/case normalized."""
    key1 = generate_cache_key("What is Glaucoma?", model="gemini-2.5-flash", max_turns=5)
    key2 = generate_cache_key("  what is glaucoma?  ", model="gemini-2.5-flash", max_turns=5)
    key3 = generate_cache_key("Different Question", model="gemini-2.5-flash", max_turns=5)

    assert key1 == key2
    assert key1 != key3
    assert len(key1) == 64  # SHA-256 length


def test_cache_telemetry_and_clear():
    """Tests cache stats and global clear_all_caches functionality."""
    qa_cache.clear()
    search_cache.clear()
    analytics_cache.clear()

    qa_cache.set("q1", {"answer": "medical advice"})
    search_cache.set("s1", [{"score": 0.95}])
    analytics_cache.set("analytics_summary", {"total_queries": 42})

    assert qa_cache.get("q1")["answer"] == "medical advice"
    assert search_cache.get("s1")[0]["score"] == 0.95
    assert analytics_cache.get("analytics_summary")["total_queries"] == 42

    all_stats = get_all_cache_stats()
    assert all_stats["qa_cache"]["current_size"] == 1
    assert all_stats["search_cache"]["current_size"] == 1
    assert all_stats["analytics_cache"]["current_size"] == 1
    assert all_stats["qa_cache"]["hits"] == 1

    clear_all_caches()
    assert qa_cache.get("q1") is None
    assert search_cache.get("s1") is None
    assert analytics_cache.get("analytics_summary") is None


def test_analytics_router_cache_endpoints():
    """Tests the /api/v1/analytics/cache/stats and /cache/clear endpoints."""
    from app.routers.analytics import router as analytics_router
    test_app = FastAPI()
    test_app.include_router(analytics_router, prefix="/api/v1/analytics")
    client = TestClient(test_app)

    # Populate cache
    qa_cache.set("sample_key", {"answer": "test"}, ttl=60)
    
    # Check stats endpoint
    res_stats = client.get("/api/v1/analytics/cache/stats", headers=ADMIN)
    assert res_stats.status_code == 200
    data = res_stats.json()
    assert "qa_cache" in data
    assert "search_cache" in data
    assert "analytics_cache" in data
    assert data["qa_cache"]["current_size"] >= 1

    # Check clear endpoint
    res_clear = client.post("/api/v1/analytics/cache/clear", headers=ADMIN)
    assert res_clear.status_code == 200
    assert res_clear.json()["status"] == "success"
    assert qa_cache.get("sample_key") is None


if __name__ == "__main__":
    print("Running in-memory rate limiter & cache test suite...")
    test_in_memory_sliding_window_limiter()
    print("[PASS] Sliding window rate limiter test")
    test_fastapi_rate_limiter_dependency()
    print("[PASS] FastAPI rate limiter dependency test")
    test_in_memory_lru_and_ttl_cache()
    print("[PASS] In-memory LRU + TTL cache test")
    test_deterministic_cache_key_generation()
    print("[PASS] Deterministic cache key generation test")
    test_cache_telemetry_and_clear()
    print("[PASS] Cache telemetry & clear test")
    test_analytics_router_cache_endpoints()
    print("[PASS] Analytics router cache endpoints test")
    print("All Rate Limiting and In-Memory Caching tests passed successfully!")



def test_client_ip_ignores_spoofed_left_entries():
    """Only the entry appended by the trusted proxy (rightmost) may identify the client."""
    from starlette.requests import Request

    scope = {"type": "http", "headers": [(b"x-forwarded-for", b"6.6.6.6, 203.0.113.9")], "client": ("10.0.0.1", 1)}
    assert get_client_ip(Request(scope)) == "203.0.113.9"
