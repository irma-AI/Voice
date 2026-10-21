import pytest
from django.core.cache import cache

from portal import synthetic


@pytest.fixture(autouse=True)
def fresh_counts() -> None:
    """The login and reset counts live in the cache, which outlives a test: each test starts with none."""
    cache.clear()


@pytest.fixture(autouse=True)
def replayable_people() -> None:
    """Each test draws the same synthetic people whatever ran before it (the seed reseeds the shared Faker), so a failure replays."""
    synthetic.fake.seed_instance(0)
    synthetic.fake.unique.clear()
