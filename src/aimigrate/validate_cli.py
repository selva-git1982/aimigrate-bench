"""Run: python -m aimigrate.validate_cli --results results/extended/results.json"""
import argparse
import csv
import json
from pathlib import Path
from .validator import validate_sql


def main():
    parser = argparse.ArgumentParser(description='Statically validate AIMigrate benchmark outputs')
    parser.add_argument('--results', type=Path, required=True, help='Existing results.json')
    parser.add_argument('--cases', type=Path, help='Original cases JSON for reference AST comparison')
    parser.add_argument('--output', type=Path, default=Path('results/validation'))
    args = parser.parse_args()
    observations = json.loads(args.results.read_text(encoding='utf-8'))
    references = {}
    if args.cases:
        references = {case['id']: case.get('expected_sql') for case in json.loads(args.cases.read_text(encoding='utf-8'))}
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for obs in observations:
        outcome = validate_sql(obs.get('output_sql', ''), obs['target_dialect'], references.get(obs['case_id']))
        rows.append({'case_id': obs['case_id'], 'method': obs['method'], **outcome.to_dict()})
    (args.output / 'validation.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    with (args.output / 'validation.csv').open('w', newline='', encoding='utf-8') as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(f'Validated {len(rows)} observations; parse successes: {sum(r["valid"] for r in rows)}')
    print('Static validation is NOT semantic equivalence or database execution.')


if __name__ == '__main__':
    main()
