from aimigrate.validator import validate_sql


def test_valid_query():
    result = validate_sql('SELECT 1', 'postgres', 'SELECT 1')
    assert result.valid and result.reference_ast_match is True
    assert result.semantic_equivalence_verified is False
    assert result.database_execution_verified is False


def test_empty_query():
    result = validate_sql('  ', 'mysql')
    assert not result.valid and result.category == 'empty_sql'


def test_unsupported_dialect():
    result = validate_sql('SELECT 1', 'oracle')
    assert not result.valid and result.category == 'unsupported_dialect'


def test_structural_difference():
    result = validate_sql('SELECT 2', 'postgres', 'SELECT 1')
    assert result.valid and result.reference_ast_match is False


def test_invalid_reference_does_not_invalidate_candidate():
    result = validate_sql('SELECT 1', 'postgres', '')
    assert result.valid and result.reference_ast_match is None
    assert result.reference_parse_error is not None
