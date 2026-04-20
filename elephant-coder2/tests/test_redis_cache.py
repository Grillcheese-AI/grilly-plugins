import pytest
from broker.store.redis_cache import RedisCache


def _redis_available(url):
    try:
        import redis
        r = redis.from_url(url)
        r.ping()
        return True
    except Exception:
        return False


REDIS_URL = "redis://localhost:6379/15"
_skip_if_no_redis = pytest.mark.skipif(
    not _redis_available(REDIS_URL), reason="Redis not available on localhost"
)


@pytest.fixture
def cache():
    c = RedisCache(url=REDIS_URL, project_hash="testproj", ttl_seconds=60)
    c.flush()
    yield c
    c.flush()


def test_fallback_when_unavailable():
    c = RedisCache(url="redis://127.0.0.1:1", project_hash="p", ttl_seconds=60)
    assert c.available is False
    c.set_memory(1, {"a": 1})
    assert c.get_memory(1) is None


@_skip_if_no_redis
def test_set_and_get_memory(cache):
    cache.set_memory(42, {"symbol": "foo", "summary": "x"})
    got = cache.get_memory(42)
    assert got["symbol"] == "foo"


@_skip_if_no_redis
def test_symbol_index(cache):
    cache.add_symbol("foo", 42)
    cache.add_symbol("foo", 43)
    assert set(cache.get_symbol_ids("foo")) == {42, 43}


@_skip_if_no_redis
def test_file_index(cache):
    cache.add_file_memory("a/b.py", 10)
    assert 10 in cache.get_file_memory_ids("a/b.py")
