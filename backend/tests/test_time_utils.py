from time_utils import hong_kong_now


def test_hong_kong_now_override(monkeypatch):
    monkeypatch.setenv("APP_TEST_NOW", "2026-05-19T08:00:00+08:00")
    assert hong_kong_now().isoformat() == "2026-05-19T08:00:00+08:00"
