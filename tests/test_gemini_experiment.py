from aimigrate.gemini_experiment import clean_sql, evaluate

CASE = {'id':'c1','source':'tsql','target':'postgres',
        'sql':'SELECT TOP 2 id FROM t ORDER BY id',
        'expected_sql':'SELECT id FROM t ORDER BY id LIMIT 2'}


def test_strip_fences():
    assert clean_sql('```sql\nSELECT 1;\n```') == 'SELECT 1;'


def test_rule_no_api_call():
    def forbidden(*args):
        raise AssertionError('should not call Gemini')
    result = evaluate(CASE, 'rule', 'fake-model', forbidden)
    assert result.parsed and result.api_calls == 0


def test_llm_mock():
    result = evaluate(CASE, 'llm', 'fake-model',
                      lambda prompt, model, temp: ('```sql\nSELECT 1\n```', 15, 5))
    assert result.parsed and result.api_calls == 1
    assert result.input_tokens == 15 and result.output_tokens == 5
    assert not result.semantic_equivalence_verified


def test_hybrid_skips_api_when_parse_valid():
    def forbidden(*args):
        raise AssertionError('valid SQL must not trigger repair')
    result = evaluate(CASE, 'hybrid', 'fake-model', forbidden)
    assert result.parsed and result.api_calls == 0 and not result.repair_attempted


def test_hybrid_repairs_failed_rule(monkeypatch):
    from aimigrate import gemini_experiment as g
    def bad_rule(*args):
        return 'SELECT FROM'
    monkeypatch.setattr(g, 'rule_based', bad_rule)
    result = g.evaluate(CASE, 'hybrid', 'fake-model',
                        lambda prompt, model, temp: ('SELECT id FROM t LIMIT 2', 20, 8))
    assert result.repair_attempted and result.repair_accepted and result.api_calls == 1
