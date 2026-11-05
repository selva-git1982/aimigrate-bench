"""Execution-triggered repair (Phase 6).

Rule-first translation with LLM repair triggered by *target execution
failure or result mismatch*, not only by static parse failure.

For each MySQL-to-PostgreSQL case:
  1. Translate with SQLGlot.
  2. Execute the source query on MySQL and the candidate on PostgreSQL.
  3. If PostgreSQL raises an error, or the normalized results differ,
     send the engine diagnostic to Gemini and request a corrected query.
  4. Re-validate every repaired candidate with the same execution check.
     At most --max-repairs repairs per case; a global --max-api-calls
     budget stops the run cleanly (resume with --resume).

Equivalence still only holds for the synthetic fixtures and engine
versions used. Results from a repaired candidate are never accepted
without re-execution.

Usage:
    export GEMINI_API_KEY=...
    export AIMIGRATE_MYSQL_*=...  AIMIGRATE_PG_*=...   (as for phase4c)
    python -m aimigrate.exec_repair \
        --cases benchmarks/cases/phase5_mysql_postgres.json \
        --output results/phase6_exec_repair --max-repairs 2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .engine import rule_based
from .gemini_experiment import clean_sql, gemini_call
from .retry import call_with_retries
from .validator import validate_sql

PROMPT_VERSION = "phase6-exec-v1"
MAX_ROWS_IN_PROMPT = 5


class BudgetExhausted(RuntimeError):
    pass


def repair_prompt(source_sql: str, candidate: str, diagnostic: str) -> str:
    """Prompt contains only benchmark SQL and synthetic-fixture diagnostics."""
    return (
        "Translate the following MySQL SQL into PostgreSQL SQL. "
        "Preserve behavior including NULL handling, ordering, and result "
        "types where possible. Do not invent tables or columns. Return only "
        "one SQL SELECT statement, no explanation or markdown.\n"
        f"Source MySQL SQL:\n{source_sql}\n"
        f"Previous PostgreSQL candidate:\n{candidate}\n"
        f"Execution diagnostic from PostgreSQL:\n{diagnostic}\n"
    )


def describe_mismatch(source_rows, target_rows) -> str:
    return (
        "The candidate executed but returned different results.\n"
        f"Expected (from MySQL, first {MAX_ROWS_IN_PROMPT} rows): "
        f"{list(source_rows)[:MAX_ROWS_IN_PROMPT]!r}\n"
        f"Got (from PostgreSQL, first {MAX_ROWS_IN_PROMPT} rows): "
        f"{list(target_rows)[:MAX_ROWS_IN_PROMPT]!r}"
    )


@dataclass
class Attempt:
    attempt: int            # 0 = rule output, 1..K = repairs
    sql: str
    parsed: bool
    executed: bool
    equivalent: bool
    error: str = ""


@dataclass
class CaseResult:
    case_id: str
    category: str
    source_error: str
    initial_outcome: str    # equivalent | mismatch | target_error | source_error
    final_outcome: str
    repairs_attempted: int
    api_calls: int
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: float
    final_sql: str
    attempts: list[Attempt] = field(default_factory=list)
    stopped_reason: str = ""


def outcome(a: Attempt) -> str:
    if a.equivalent:
        return "equivalent"
    return "mismatch" if a.executed else "target_error"


def run_case(
    case: dict,
    source_rows,
    source_error: str,
    execute_target: Callable[[str], list],
    rows_equal: Callable[[list, list, bool], bool],
    caller: Callable[[str, str, float], tuple[str, int | None, int | None]],
    model: str,
    max_repairs: int,
    spend: Callable[[], None],
    max_attempts: int = 3,
) -> CaseResult:
    """Translate, execute, and repair one case. DB access is injected."""
    start = time.perf_counter()
    ordered = bool(case.get("ordered", False))
    api_calls, tin, tout, seen_usage = 0, 0, 0, False
    attempts: list[Attempt] = []
    stopped = ""

    def check(sql: str, n: int) -> tuple[Attempt, list | None]:
        parsed = validate_sql(sql, "postgres").valid if sql else False
        try:
            rows = execute_target(sql)
        except Exception as exc:  # engine error is the diagnostic
            msg = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
            return Attempt(n, sql, parsed, False, False, msg), None
        eq = rows_equal(source_rows, rows, ordered)
        return Attempt(n, sql, parsed, True, eq), rows

    if source_error:
        return CaseResult(case["id"], case.get("category", ""), source_error,
                          "source_error", "source_error", 0, 0, None, None,
                          0.0, "", [], "source query failed on MySQL")

    try:
        sql = rule_based(case["sql"], "mysql", "postgres")
    except Exception as exc:
        sql = ""
        attempts.append(Attempt(0, "", False, False, False,
                                f"Rule conversion failed: {exc}"))
        last_rows = None
    if sql:
        a, last_rows = check(sql, 0)
        attempts.append(a)

    repairs = 0
    while not attempts[-1].equivalent and repairs < max_repairs:
        last = attempts[-1]
        diagnostic = (
            last.error if not last.executed
            else describe_mismatch(source_rows, last_rows or [])
        )

        def call():
            return caller(repair_prompt(case["sql"], last.sql, diagnostic),
                          model, 0.0)

        def count():
            nonlocal api_calls
            spend()             # raises BudgetExhausted before the call
            api_calls += 1

        try:
            text, i, o = call_with_retries(call, max_attempts=max_attempts,
                                           on_attempt=count)
        except BudgetExhausted:
            stopped = "api budget exhausted"
            break
        except Exception as exc:
            stopped = f"API error: {type(exc).__name__}: {exc}"
            break
        if i is not None:
            tin += i; seen_usage = True
        if o is not None:
            tout += o; seen_usage = True
        repairs += 1
        a, last_rows = check(clean_sql(text), repairs)
        attempts.append(a)

    return CaseResult(
        case_id=case["id"],
        category=case.get("category", ""),
        source_error="",
        initial_outcome=outcome(attempts[0]),
        final_outcome=outcome(attempts[-1]),
        repairs_attempted=repairs,
        api_calls=api_calls,
        input_tokens=tin if seen_usage else None,
        output_tokens=tout if seen_usage else None,
        duration_ms=round((time.perf_counter() - start) * 1000, 3),
        final_sql=attempts[-1].sql,
        attempts=attempts,
        stopped_reason=stopped,
    )


def summarize(results: list[CaseResult]) -> dict:
    n = len(results)
    init_eq = sum(r.initial_outcome == "equivalent" for r in results)
    final_eq = sum(r.final_outcome == "equivalent" for r in results)
    return {
        "cases": n,
        "initial_equivalent": init_eq,
        "final_equivalent": final_eq,
        "cases_repaired": sum(r.initial_outcome != "equivalent"
                              and r.final_outcome == "equivalent" for r in results),
        "cases_regressed": sum(r.initial_outcome == "equivalent"
                               and r.final_outcome != "equivalent" for r in results),
        "repairs_attempted": sum(r.repairs_attempted for r in results),
        "api_calls": sum(r.api_calls for r in results),
        "unresolved": [r.case_id for r in results if r.final_outcome != "equivalent"],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Phase 6: execution-triggered repair")
    p.add_argument("--cases", type=Path,
                   default=Path("benchmarks/cases/phase5_mysql_postgres.json"))
    p.add_argument("--output", type=Path, default=Path("results/phase6_exec_repair"))
    p.add_argument("--model", default="gemini-flash-latest")
    p.add_argument("--max-repairs", type=int, default=2)
    p.add_argument("--max-api-calls", type=int, default=20)
    p.add_argument("--max-attempts", type=int, default=3,
                   help="per-call attempts for retryable 429/5xx errors")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args(argv)

    from . import phase4c as db   # imported lazily: needs DB drivers

    raw = args.cases.read_bytes()
    cases = [c for c in json.loads(raw)
             if c.get("source") == "mysql" and c.get("target") == "postgres"]
    args.output.mkdir(parents=True, exist_ok=True)
    obs_path = args.output / "observations.json"
    done = {}
    if args.resume and obs_path.exists():
        for r in json.loads(obs_path.read_text(encoding="utf-8")):
            if not r.get("stopped_reason"):
                done[r["case_id"]] = r

    budget = {"left": args.max_api_calls}

    def spend():
        if budget["left"] <= 0:
            raise BudgetExhausted()
        budget["left"] -= 1

    meta = {
        "phase": "6-exec-repair",
        "prompt_version": PROMPT_VERSION,
        "model": args.model,
        "max_repairs": args.max_repairs,
        "max_api_calls": args.max_api_calls,
        "cases_file": str(args.cases),
        "cases_sha256": hashlib.sha256(raw).hexdigest(),
        "python": platform.python_version(),
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        import sqlglot
        meta["sqlglot"] = sqlglot.__version__
    except Exception:
        pass

    my = db.connect_mysql()
    pg = db.connect_postgres()
    results: list[dict] = []
    try:
        db.seed_databases(my, pg)
        with my.cursor() as mc, pg.cursor() as pc:
            mc.execute("SELECT VERSION()"); meta["mysql_version"] = mc.fetchone()[0]
            pc.execute("SHOW server_version"); meta["postgres_version"] = pc.fetchone()[0]
            pc.execute("SET statement_timeout = 10000")

            def execute_target(sql: str):
                pc.execute(db.validate_select(sql))
                return pc.fetchall()

            for case in cases:
                if case["id"] in done:
                    results.append(done[case["id"]]); continue
                src_rows, src_err = None, ""
                try:
                    mc.execute(db.validate_select(case["sql"]))
                    src_rows = mc.fetchall()
                except Exception as exc:
                    src_err = f"{type(exc).__name__}: {exc}"
                r = run_case(case, src_rows, src_err, execute_target,
                             db.rows_equal, gemini_call, args.model,
                             args.max_repairs, spend, args.max_attempts)
                results.append(asdict(r))
                print(f"{r.case_id}: {r.initial_outcome} -> {r.final_outcome} "
                      f"(repairs={r.repairs_attempted}) {r.stopped_reason}")
                obs_path.write_text(json.dumps(results, indent=2, default=str),
                                    encoding="utf-8")
    finally:
        my.close(); pg.close()

    summary = summarize([CaseResult(**{**r, "attempts": [Attempt(**a) for a in r["attempts"]]})
                         for r in results])
    meta["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (args.output / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
