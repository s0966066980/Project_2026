"""What the maintenance panel is allowed to claim about a dependency.

The panel exists so an operator can tell whether a customer can order right now.
That makes two failure modes expensive in opposite directions: reporting an
outage that is not happening sends someone to fix nothing, and reporting health
that is not there leaves a broken kiosk running. Every case here is about keeping
the claim no stronger than the observation.
"""

from modules.service_health.module import WATCHED_SERVICES, ServiceHealthModule


class _Probe:
    def __init__(self, observations=None, raises=None):
        self._observations = observations or {}
        self._raises = raises or {}
        self.asked: list[str] = []

    def probe(self, key):
        self.asked.append(key)
        if key in self._raises:
            raise self._raises[key]
        return self._observations.get(key)


def _snapshot(observations=None, raises=None, **kwargs):
    probe = _Probe(observations, raises)
    module = ServiceHealthModule(probe=probe, **kwargs)
    return probe, {status.key: status for status in module.snapshot()}


def test_exactly_the_four_watched_services_are_reported():
    probe, snapshot = _snapshot()

    assert [key for key, _ in WATCHED_SERVICES] == ["ui_api", "ollama", "r1_omni", "rag_retrieval"]
    assert set(snapshot) == {"ui_api", "ollama", "r1_omni", "rag_retrieval"}
    assert probe.asked == ["ui_api", "ollama", "r1_omni", "rag_retrieval"]


def test_every_service_carries_a_readable_label():
    _, snapshot = _snapshot()

    assert all(status.label.strip() for status in snapshot.values())


def test_a_healthy_service_reports_its_latency():
    _, snapshot = _snapshot({"ollama": {"status": "ok", "latency_ms": 42, "observed_at": "2026-08-07T00:00:00+00:00"}})

    assert snapshot["ollama"].status == "ok"
    assert snapshot["ollama"].latency_ms == 42
    assert snapshot["ollama"].observed_at == "2026-08-07T00:00:00+00:00"
    assert snapshot["ollama"].safe_error == ""


# Answering slowly is not the same as answering. An operator watching a kiosk stall
# should see that without having to read and interpret the number.
def test_a_slow_answer_is_degraded_rather_than_healthy():
    _, snapshot = _snapshot({"ollama": {"status": "ok", "latency_ms": 5000}}, slow_ms=2000)

    assert snapshot["ollama"].status == "degraded"
    assert snapshot["ollama"].latency_ms == 5000


def test_a_fast_answer_stays_healthy():
    _, snapshot = _snapshot({"ollama": {"status": "ok", "latency_ms": 1999}}, slow_ms=2000)

    assert snapshot["ollama"].status == "ok"


# A probe that has not run yet says nothing about the service.
def test_an_unobserved_service_is_unknown_not_down():
    _, snapshot = _snapshot()

    assert snapshot["r1_omni"].status == "unknown"
    assert snapshot["r1_omni"].latency_ms is None


def test_a_probe_that_raises_reports_unknown_with_the_reason():
    _, snapshot = _snapshot(raises={"r1_omni": RuntimeError("probe_misconfigured")})

    assert snapshot["r1_omni"].status == "unknown"
    assert "probe_misconfigured" in snapshot["r1_omni"].safe_error


def test_an_unconfigured_service_is_distinguished_from_a_broken_one():
    _, snapshot = _snapshot({"r1_omni": {"status": "not_configured", "safe_error": "服務位址未設定"}})

    assert snapshot["r1_omni"].status == "not_configured"


def test_an_unrecognised_status_is_never_passed_through_as_healthy():
    _, snapshot = _snapshot({"ollama": {"status": "probably_fine", "latency_ms": 10}})

    assert snapshot["ollama"].status == "unknown"


def test_a_safe_error_is_bounded_so_a_stack_trace_cannot_reach_the_panel():
    _, snapshot = _snapshot({"ollama": {"status": "down", "safe_error": "x" * 5000}})

    assert len(snapshot["ollama"].safe_error) == 200


def test_a_negative_latency_is_not_reported():
    _, snapshot = _snapshot({"ollama": {"status": "ok", "latency_ms": -5}})

    assert snapshot["ollama"].latency_ms == 0


def test_the_panel_shape_is_stable_for_every_service():
    _, snapshot = _snapshot()

    for status in snapshot.values():
        assert set(status.as_dict()) == {
            "key",
            "label",
            "status",
            "latency_ms",
            "observed_at",
            "safe_error",
        }
