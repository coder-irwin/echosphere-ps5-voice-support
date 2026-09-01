import pytest

from app.factory import build_session, get_store


@pytest.fixture
def store():
    s = get_store()
    s.reset()
    return s


@pytest.fixture
def session(store):
    s = build_session("test-session", store=store)
    s.open()
    return s
