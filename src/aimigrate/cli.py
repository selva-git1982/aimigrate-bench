import argparse
import csv
import json
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sqlglot
from .engine import run_suite


def main():
    parser = argparse.ArgumentParser(description="Run AIMigrate-Bench")
    parser.add_argument("--cases", type=Path, default=Path("benchmarks/cases/smoke.json"))
    parser.add_argument("--methods", nargs="+", choices=["rule", "llm", "hybrid"], default=["rule"])
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = run_suite(args.cases, args.methods)
    rows = [asdict(r) for r in results]
    (args.output / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with (args.output / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else list(asdict(__import__('aimigrate.engine', fromlist=['Result']).Result('', '', '', '', '', False, None, 0))))
        writer.writeheader()
        writer.writerows(rows)
    metadata = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
                "platform": platform.platform(), "sqlglot": sqlglot.__version__, "methods": args.methods,
                "case_file": str(args.cases), "case_count": len(set(r.case_id for r in results))}
    (args.output / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} observations to {args.output}")
    print("Parse success is NOT proof of semantic equivalence.")

if __name__ == "__main__":
    main()
