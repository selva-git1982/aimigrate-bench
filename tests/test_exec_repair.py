from aimigrate.exec_repair import BudgetExhausted, run_case, summarize


def eq(a, b, ordered):
    return list(a) == list(b)


def failing_then_fixed_executor(sql):
    if "YEAR(" in sql.upper() and "EXTRACT" not in sql.upper():
        raise RuntimeError("function year(date) does not exist")
    return [(2026,)]


CASE = {"id": "c1", "category": "date_time", "ordered": True,
        "sql": "SELECT YEAR('2026-11-04') AS y"}


def test_repair_triggered_by_execution_error_and_revalidated():
    prompts = []

    def caller(prompt, model, temperature):
        prompts.append(prompt)
        return "```sql\nSELECT EXTRACT(YEAR FROM DATE '2026-11-04') AS y\n```", 10, 5

    r = run_case(CASE, [(2026,)], "", failing_then_fixed_executor, eq, caller,
                 "m", max_repairs=2, spend=lambda: None)
    assert r.initial_outcome == "target_error"
    assert r.final_outcome == "equivalent"
    assert r.repairs_attempted == 1 and r.api_calls == 1
    assert "does not exist" in prompts[0]
    assert r.attempts[-1].executed and r.attempts[-1].equivalent


def test_mismatch_triggers_repair_and_bad_repair_is_not_accepted():
    def wrong_executor(sql):
        return [(1999,)]

    r = run_case(CASE | {"sql": "SELECT 2026 AS y"}, [(2026,)], "", wrong_executor,
                 eq, lambda p, m, t: ("SELECT 1999 AS y", None, None), "m",
                 max_repairs=2, spend=lambda: None)
    assert r.initial_outcome == "mismatch"
    assert r.final_outcome == "mismatch"
    assert r.repairs_attempted == 2


def test_equivalent_case_makes_no_api_call():
    def boom(*_):
        raise AssertionError("should not call model")

    r = run_case(CASE | {"sql": "SELECT 2026 AS y"}, [(2026,)], "",
                 lambda s: [(2026,)], eq, boom, "m", 2, spend=lambda: None)
    assert r.api_calls == 0 and r.final_outcome == "equivalent"


def test_budget_stops_cleanly():
    def spend():
        raise BudgetExhausted()

    r = run_case(CASE, [(2026,)], "", failing_then_fixed_executor, eq,
                 lambda p, m, t: ("x", None, None), "m", 2, spend=spend)
    assert r.stopped_reason == "api budget exhausted"
    assert r.api_calls == 0
    s = summarize([r])
    assert s["unresolved"] == ["c1"]
