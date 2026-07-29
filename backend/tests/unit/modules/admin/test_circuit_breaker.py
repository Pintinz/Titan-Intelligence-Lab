from datetime import datetime, timedelta, timezone

from modules.admin.application.circuit_breaker import CircuitBreaker
from modules.admin.domain.value_objects import CircuitState

T0 = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def test_circuit_starts_closed():
    breaker = CircuitBreaker()

    assert breaker.state_of("api_football") is CircuitState.CLOSED
    assert breaker.allow_request("api_football", T0)


def test_circuit_opens_after_failure_threshold():
    breaker = CircuitBreaker(failure_threshold=3)

    for _ in range(3):
        breaker.record_failure("api_football", T0)

    assert breaker.state_of("api_football") is CircuitState.OPEN
    assert not breaker.allow_request("api_football", T0)


def test_circuit_stays_closed_below_threshold():
    breaker = CircuitBreaker(failure_threshold=3)

    breaker.record_failure("api_football", T0)
    breaker.record_failure("api_football", T0)

    assert breaker.state_of("api_football") is CircuitState.CLOSED


def test_success_resets_failure_count():
    breaker = CircuitBreaker(failure_threshold=3)

    breaker.record_failure("api_football", T0)
    breaker.record_failure("api_football", T0)
    breaker.record_success("api_football")
    breaker.record_failure("api_football", T0)
    breaker.record_failure("api_football", T0)

    assert breaker.state_of("api_football") is CircuitState.CLOSED


def test_circuit_half_opens_after_recovery_timeout():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=timedelta(seconds=30))

    breaker.record_failure("api_football", T0)
    assert not breaker.allow_request("api_football", T0 + timedelta(seconds=10))

    allowed = breaker.allow_request("api_football", T0 + timedelta(seconds=31))

    assert allowed
    assert breaker.state_of("api_football") is CircuitState.HALF_OPEN


def test_half_open_failure_reopens_circuit():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=timedelta(seconds=30))
    breaker.record_failure("api_football", T0)
    breaker.allow_request("api_football", T0 + timedelta(seconds=31))  # -> HALF_OPEN

    breaker.record_failure("api_football", T0 + timedelta(seconds=31))

    assert breaker.state_of("api_football") is CircuitState.OPEN


def test_half_open_success_closes_circuit():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=timedelta(seconds=30))
    breaker.record_failure("api_football", T0)
    breaker.allow_request("api_football", T0 + timedelta(seconds=31))  # -> HALF_OPEN

    breaker.record_success("api_football")

    assert breaker.state_of("api_football") is CircuitState.CLOSED


def test_providers_have_independent_circuits():
    breaker = CircuitBreaker(failure_threshold=1)

    breaker.record_failure("api_football", T0)

    assert breaker.state_of("api_football") is CircuitState.OPEN
    assert breaker.state_of("api_basketball") is CircuitState.CLOSED
