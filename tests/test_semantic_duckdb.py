import pytest
pytest.importorskip('duckdb')
from aimigrate.semantic_duckdb import run_probe, canonical


def test_equal_sql():
    result = run_probe({'id': 'same', 'expected_sql': 'SELECT 1', 'candidate_sql': 'SELECT 1'})
    assert result.equal and not result.cross_database_verified


def test_null_semantic_difference():
    result = run_probe({'id': 'null', 'expected_sql': "SELECT 'Hello' || NULL", 'candidate_sql': "SELECT CONCAT('Hello', NULL)"})
    assert not result.equal and not result.error


def test_unordered_multiset():
    assert canonical([(1,), (2,), (2,)], False) == canonical([(2,), (1,), (2,)], False)
    assert canonical([(1,), (2,), (2,)], False) != canonical([(1,), (1,), (2,)], False)


def test_ordered_rows():
    assert canonical([(1,), (2,)], True) != canonical([(2,), (1,)], True)


def test_sql_error_is_recorded():
    result = run_probe({'id': 'bad', 'expected_sql': 'SELECT 1', 'candidate_sql': 'SELECT * FROM missing_table'})
    assert not result.equal and result.error
