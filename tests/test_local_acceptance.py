"""The real-model acceptance command must fail closed when inference is unverified."""

import pytest

from copilot import local_check


@pytest.mark.parametrize(
    "report,expected",
    [
        ({"status": "blocked_runtime", "passed": 0}, 1),
        ({"status": "failed", "passed": 4}, 1),
        ({"status": "passed", "passed": 4}, 1),
        ({"status": "passed", "passed": 5}, 0),
    ],
)
def test_local_acceptance_exit_status(monkeypatch, report, expected):
    monkeypatch.setattr(local_check, "check", lambda: report)
    assert local_check.main() == expected


def test_scenario_exception_remains_a_failure_and_next_case_runs():
    def broken():
        raise RuntimeError("model response failed")

    failed = local_check.record_case("contact", broken)
    assert failed["status"] == "failed" and failed["error_type"] == "RuntimeError"
    assert local_check.record_case("invoice", lambda: {"status": "passed"})["status"] == "passed"
