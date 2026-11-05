"""Static SQL validation. No database execution or semantic-equivalence claims."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Optional
import sqlglot
from sqlglot import errors

SUPPORTED_DIALECTS = frozenset({'tsql', 'mysql', 'postgres'})

@dataclass
class ValidationResult:
    valid: bool
    category: str
    message: str
    dialect: str
    statement_count: int
    normalized_sql: Optional[str]
    reference_ast_match: Optional[bool]
    reference_parse_error: Optional[str]
    semantic_equivalence_verified: bool = False
    database_execution_verified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _parse(sql: str, dialect: str):
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError('SQL is empty')
    statements = sqlglot.parse(sql, read=dialect, error_level=errors.ErrorLevel.RAISE)
    if not statements or any(stmt is None for stmt in statements):
        raise ValueError('SQL has no complete statements')
    return statements


def validate_sql(sql: str, target_dialect: str, expected_sql: Optional[str] = None) -> ValidationResult:
    """Parse target SQL and optionally compare canonical ASTs with a reference.

    AST equality is structural only; it is NOT proof of semantic equivalence.
    SQLGlot can accept constructs not supported by the actual database engine.
    """
    if target_dialect not in SUPPORTED_DIALECTS:
        return ValidationResult(False, 'unsupported_dialect', f'Unsupported dialect: {target_dialect}',
                                target_dialect, 0, None, None, None)
    try:
        statements = _parse(sql, target_dialect)
    except ValueError as exc:
        return ValidationResult(False, 'empty_sql', str(exc), target_dialect, 0, None, None, None)
    except errors.ParseError as exc:
        return ValidationResult(False, 'parse_error', str(exc), target_dialect, 0, None, None, None)
    except errors.TokenError as exc:
        return ValidationResult(False, 'token_error', str(exc), target_dialect, 0, None, None, None)
    except Exception as exc:
        return ValidationResult(False, 'validation_error', f'{type(exc).__name__}: {exc}',
                                target_dialect, 0, None, None, None)

    canonical = '; '.join(s.sql(dialect=target_dialect) for s in statements)
    ast_match = None
    reference_error = None
    if expected_sql is not None:
        try:
            expected = _parse(expected_sql, target_dialect)
            ast_match = len(statements) == len(expected) and all(
                a == b for a, b in zip(statements, expected)
            )
        except Exception as exc:
            reference_error = f'{type(exc).__name__}: {exc}'

    return ValidationResult(True, 'parse_success', 'Target-dialect parse succeeded; execution not tested',
                            target_dialect, len(statements), canonical, ast_match, reference_error)
