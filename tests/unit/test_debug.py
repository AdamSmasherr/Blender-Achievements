"""Unit tests for achievements/debug.py: the is_enabled() cache and the
per-call-site failure counter that prints a warning even without Dev Tools."""

import pytest

from achievements import debug


@pytest.fixture(autouse=True)
def _clean_debug_state(monkeypatch):
    """Every test gets a fresh cache/counter state and a controllable clock,
    so tests can't leak into each other or depend on real wall-clock time."""
    monkeypatch.setattr(debug, "_enabled_cache", None)
    monkeypatch.setattr(debug, "_enabled_cache_time", 0.0)
    debug.reset_error_counts()
    yield
    debug.reset_error_counts()


def test_is_enabled_caches_between_calls_within_ttl(monkeypatch):
    calls = []

    def fake_resolve():
        calls.append(1)
        return True

    monkeypatch.setattr(debug, "_resolve_enabled", fake_resolve)
    fake_time = [100.0]
    monkeypatch.setattr(debug.time, "monotonic", lambda: fake_time[0])

    assert debug.is_enabled() is True
    assert debug.is_enabled() is True
    assert debug.is_enabled() is True
    assert len(calls) == 1, "is_enabled() re-resolved within the cache TTL"


def test_is_enabled_re_resolves_after_ttl_expires(monkeypatch):
    calls = []

    def fake_resolve():
        calls.append(1)
        return len(calls) == 1  # True on first resolve, False afterwards

    monkeypatch.setattr(debug, "_resolve_enabled", fake_resolve)
    fake_time = [0.0]
    monkeypatch.setattr(debug.time, "monotonic", lambda: fake_time[0])

    assert debug.is_enabled() is True
    fake_time[0] += debug._ENABLED_CACHE_TTL + 0.1
    assert debug.is_enabled() is False
    assert len(calls) == 2


def test_log_is_silent_without_devtools_enabled(monkeypatch, capsys):
    monkeypatch.setattr(debug, "is_enabled", lambda: False)
    debug.log("some.py:1", ValueError("boom"))
    captured = capsys.readouterr()
    assert captured.out == ""


def test_log_prints_traceback_when_devtools_enabled(monkeypatch, capsys):
    monkeypatch.setattr(debug, "is_enabled", lambda: True)
    try:
        raise ValueError("boom")
    except ValueError as err:
        debug.log("some.py:1", err)
    captured = capsys.readouterr()
    assert "some.py:1" in captured.out
    assert "boom" in captured.out


def test_repeated_failures_at_same_site_print_one_warning_regardless_of_devtools(monkeypatch, capsys):
    monkeypatch.setattr(debug, "is_enabled", lambda: False)  # devtools off throughout

    for _ in range(debug._WARN_THRESHOLD - 1):
        debug.log("flaky.py:42", RuntimeError("x"))
    assert capsys.readouterr().out == "", "warned before reaching the threshold"

    debug.log("flaky.py:42", RuntimeError("x"))  # the Nth failure
    out = capsys.readouterr().out
    assert "flaky.py:42" in out
    assert "failed" in out.lower()

    # Further failures at the same site must not spam another warning.
    debug.log("flaky.py:42", RuntimeError("x"))
    assert capsys.readouterr().out == ""


def test_different_call_sites_are_tracked_independently(monkeypatch, capsys):
    monkeypatch.setattr(debug, "is_enabled", lambda: False)

    for _ in range(debug._WARN_THRESHOLD - 1):
        debug.log("site_a", RuntimeError("x"))
    for _ in range(debug._WARN_THRESHOLD - 1):
        debug.log("site_b", RuntimeError("x"))
    assert capsys.readouterr().out == "", "neither site should have tripped yet"

    debug.log("site_a", RuntimeError("x"))
    out = capsys.readouterr().out
    assert "site_a" in out and "site_b" not in out


def test_guarded_swallows_exception_and_logs(monkeypatch):
    logged = []
    monkeypatch.setattr(debug, "log", lambda msg, err=None: logged.append((msg, err)))

    ran_after = False
    with debug.guarded("some.py:site"):
        raise ValueError("boom")
    ran_after = True

    assert ran_after, "exception inside the block must not propagate"
    assert len(logged) == 1
    assert logged[0][0] == "some.py:site"
    assert isinstance(logged[0][1], ValueError)


def test_guarded_lets_the_block_run_normally_when_no_exception():
    calls = []
    with debug.guarded("some.py:site"):
        calls.append(1)
    assert calls == [1]


def test_guarded_value_returns_function_result_on_success():
    assert debug.guarded_value("some.py:site", lambda: 42, default=-1) == 42


def test_guarded_value_returns_default_and_logs_on_exception(monkeypatch):
    logged = []
    monkeypatch.setattr(debug, "log", lambda msg, err=None: logged.append((msg, err)))

    def boom():
        raise RuntimeError("x")

    result = debug.guarded_value("some.py:site", boom, default="fallback")

    assert result == "fallback"
    assert logged[0][0] == "some.py:site"
    assert isinstance(logged[0][1], RuntimeError)


def test_reset_error_counts_allows_the_warning_to_fire_again(monkeypatch, capsys):
    monkeypatch.setattr(debug, "is_enabled", lambda: False)

    for _ in range(debug._WARN_THRESHOLD):
        debug.log("flaky.py:42", RuntimeError("x"))
    assert "flaky.py:42" in capsys.readouterr().out

    debug.reset_error_counts()

    for _ in range(debug._WARN_THRESHOLD - 1):
        debug.log("flaky.py:42", RuntimeError("x"))
    assert capsys.readouterr().out == ""

    debug.log("flaky.py:42", RuntimeError("x"))
    assert "flaky.py:42" in capsys.readouterr().out
