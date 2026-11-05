"""Phase 4A: controlled, DuckDB-only result-equivalence probes.

These probes do NOT establish source/target database equivalence.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


def normalize(value):
    if value is None:
        return ('null',)
    if isinstance(value, float) and math.isnan(value):
        return ('nan',)
    if isinstance(value, (bytes, bytearray)):
        return ('bytes', bytes(value).hex())
    return (type(value).__name__, str(value))


def canonical(rows, ordered):
    normalized = [tuple(normalize(x) for x in row) for row in rows]
    if ordered:
        return normalized
    return Counter(normalized)


@dataclass
class ProbeResult:
    case_id: str
    equal: bool
    expected_rows: str
    candidate_rows: str
    error: str
    engine: str = 'duckdb'
    cross_database_verified: bool = False


def run_probe(probe: dict) -> ProbeResult:
    import duckdb
    connection = duckdb.connect(':memory:')
    expected_rows, candidate_rows, error = [], [], ''
    try:
        for statement in probe.get('setup_sql', []):
            connection.execute(statement)
        expected_rows = connection.execute(probe['expected_sql']).fetchall()
        candidate_rows = connection.execute(probe['candidate_sql']).fetchall()
        equal = canonical(expected_rows, probe.get('ordered', False)) == canonical(candidate_rows, probe.get('ordered', False))
    except Exception as exc:
        equal = False
        error = f'{type(exc).__name__}: {exc}'
    finally:
        connection.close()
    return ProbeResult(case_id=probe['id'], equal=equal,
                       expected_rows=repr(expected_rows), candidate_rows=repr(candidate_rows), error=error)


def main():
    parser = argparse.ArgumentParser(description='DuckDB-only semantic probe runner (not cross-database verification)')
    parser.add_argument('--cases', type=Path, default=Path('benchmarks/semantic/duckdb_probes.json'))
    parser.add_argument('--output', type=Path, default=Path('results/phase4a'))
    args = parser.parse_args()
    probes = json.loads(args.cases.read_text(encoding='utf-8'))
    if not isinstance(probes, list) or len({p['id'] for p in probes}) != len(probes):
        parser.error('Expected list of probes with unique IDs')
    results = [run_probe(probe) for probe in probes]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'observations.json').write_text(json.dumps([asdict(r) for r in results], indent=2), encoding='utf-8')
    with (args.output / 'observations.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(ProbeResult.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(r) for r in results)
    for r in results:
        print(f'{r.case_id}: equivalent_on_duckdb={r.equal} error={r.error[:120]}')
    print(f'{sum(r.equal for r in results)}/{len(results)} DuckDB-only probes equivalent; cross-database semantics NOT verified.')


if __name__ == '__main__':
    main()
