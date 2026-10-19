import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def fresh_counts() -> None:
    """The login and reset counts live in the cache, which outlives a test: each test starts with none."""
    cache.clear()
