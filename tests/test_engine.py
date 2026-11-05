from aimigrate.engine import parseable, rule_based, run_case

def test_tsql_top_conversion():
    sql = rule_based("SELECT TOP 5 id FROM customers ORDER BY id", "tsql", "postgres")
    assert "LIMIT 5" in sql.upper()
    assert parseable(sql, "postgres")

def test_invalid_sql():
    assert not parseable("", "postgres")

def test_rule_case_has_measured_time():
    case = {"id":"demo", "source":"mysql", "target":"postgres", "sql":"SELECT 1"}
    result = run_case(case, "rule")
    assert result.parsed
    assert result.duration_ms >= 0
    assert result.exact_match is None

def test_unsupported_dialect():
    try:
        run_case({"id":"bad", "source":"oracle", "target":"postgres", "sql":"SELECT 1"}, "rule")
        assert False
    except ValueError:
        pass
