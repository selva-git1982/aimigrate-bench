from aimigrate.retry import call_with_retries
import pytest


class FakeHTTPError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(f'{code} error')


def test_retries_503_then_succeeds():
    attempts, waits = [], []
    def operation():
        attempts.append(1)
        if len(attempts) < 3:
            raise FakeHTTPError(503)
        return 'SELECT 1'
    assert call_with_retries(operation, sleep=waits.append) == 'SELECT 1'
    assert len(attempts) == 3
    assert waits == [1.0, 2.0]


def test_404_not_retried():
    attempts = []
    def operation():
        attempts.append(1)
        raise FakeHTTPError(404)
    with pytest.raises(FakeHTTPError):
        call_with_retries(operation, sleep=lambda _: None)
    assert len(attempts) == 1


def test_budget_checked_before_each_attempt():
    attempts = []
    def before():
        if len(attempts) >= 1:
            raise RuntimeError('API call budget exhausted')
    def operation():
        attempts.append(1)
        raise FakeHTTPError(503)
    with pytest.raises(RuntimeError, match='budget exhausted'):
        call_with_retries(operation, on_attempt=before, sleep=lambda _: None)
    assert len(attempts) == 1


def test_retry_429():
    attempts = []
    def operation():
        attempts.append(1)
        if len(attempts) == 1:
            raise FakeHTTPError(429)
        return 'ok'
    assert call_with_retries(operation, sleep=lambda _: None) == 'ok'
    assert len(attempts) == 2
