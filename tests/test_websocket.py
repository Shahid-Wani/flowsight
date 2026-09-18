"""Tests for the WebSocket live-feed helpers."""


def test_recent_window_returns_relative_flux_window():
    """The window must be a relative duration plus an explicit now()."""
    from flowsight.api.websocket import _recent_window

    assert _recent_window(30) == ("-30s", "now()")
    assert _recent_window(300) == ("-300s", "now()")
    assert _recent_window(5) == ("-5s", "now()")


def test_recent_window_output_passes_storage_validation():
    """Regression: the broadcast window must be accepted by storage.

    The old inline window used offset-less datetime.utcnow().isoformat()
    values ("2026-09-17T10:30:00.123456"), which normalize_time_range
    rejects - so every broadcast failed silently behind a logged
    warning and the live feed never delivered data.
    """
    from flowsight.api.websocket import _recent_window
    from flowsight.storage.influxdb import normalize_time_range

    start, stop = _recent_window(30)

    assert normalize_time_range(start, stop) == ("-30s", "now()")
