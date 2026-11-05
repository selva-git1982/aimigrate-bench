from aimigrate.phase4c import normalize, rows_equal, rewrite_tables, validate_select


def test_null_normalization():
    assert normalize(None) == ("NULL",)


def test_numeric_normalization():
    assert normalize(1) == normalize(1.0)


def test_table_rewrite_is_isolated():
    assert "aimigrate_bench_employees" in rewrite_tables(
        "SELECT * FROM employees"
    )


def test_select_validation_rejects_multiple_statements():
    try:
        validate_select("SELECT 1; SELECT 2")
    except ValueError:
        pass
    else:
        raise AssertionError("multiple statements should be rejected")


def test_multiset_comparison_preserves_duplicates():
    assert rows_equal([(1,), (1,), (2,)], [(2,), (1,), (1,)])
    assert not rows_equal([(1,), (1,)], [(1,), (2,)])
