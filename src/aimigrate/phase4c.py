
"""
AIMigrate-Bench Phase 4C
Live MySQL-to-PostgreSQL semantic equivalence evaluation.

Compares SQLGlot, Gemini, and hybrid-generated SQL against
the original MySQL query using actual database execution.

Requires:
    mysql-connector-python
    psycopg[binary]

Uses isolated synthetic benchmark tables only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time

from collections import Counter
from decimal import Decimal
from pathlib import Path

import mysql.connector
import psycopg


# ---------------------------------------------------------
# 1. Benchmark configuration
# ---------------------------------------------------------

TABLE_MAP = {
    "customers": "aimigrate_bench_customers",
    "employees": "aimigrate_bench_employees",
}

CUSTOMERS = [
    (1, "Alice"),
    (2, None),
    (3, "Bob"),
    (4, ""),
]

EMPLOYEES = [
    (1, "Ada", "Lovelace"),
    (2, None, "NoFirst"),
    (3, "NoLast", None),
    (4, None, None),
    (5, "Grace", "Hopper"),
]


# ---------------------------------------------------------
# 2. Normalize database values
# ---------------------------------------------------------

def normalize(value):
    """Normalize values returned by MySQL and PostgreSQL."""

    if value is None:
        return ("NULL",)

    if isinstance(value, bool):
        return ("BOOLEAN", value)

    if isinstance(value, Decimal):
        return ("NUMBER", str(value.normalize()))

    if isinstance(value, (int, float)):
        return ("NUMBER", str(Decimal(str(value)).normalize()))

    if isinstance(value, (bytes, bytearray)):
        return ("BYTES", bytes(value).hex())

    return (type(value).__name__, str(value))


# Backward-compatible alias.
def norm(value):
    return normalize(value)


def normalize_rows(rows):
    return [
        tuple(normalize(value) for value in row)
        for row in rows
    ]


# ---------------------------------------------------------
# 3. Compare result sets
# ---------------------------------------------------------

def rows_equal(source, target, ordered=False):
    """
    Compare database result sets.

    ordered=False:
        Compare as multisets, preserving duplicate counts.

    ordered=True:
        Compare row order as well.
    """

    left = normalize_rows(source)
    right = normalize_rows(target)

    if ordered:
        return left == right

    return Counter(left) == Counter(right)


# ---------------------------------------------------------
# 4. Rewrite table names to isolated benchmark tables
# ---------------------------------------------------------

def rewrite_tables(sql):
    """
    Rewrite known table names to isolated AIMigrate tables.

    This allows testing without modifying ordinary
    customers or employees tables.
    """

    for original, replacement in TABLE_MAP.items():

        pattern = rf"\b{re.escape(original)}\b"

        sql = re.sub(
            pattern,
            replacement,
            sql,
            flags=re.IGNORECASE,
        )

    return sql


# ---------------------------------------------------------
# 5. Validate SQL statements
# ---------------------------------------------------------

def validate_select(sql):
    """
    Accept only a single SELECT statement from the
    controlled benchmark inputs.

    This is a basic guard, not a complete SQL security
    boundary. Use dedicated disposable databases.
    """

    sql = (sql or "").strip()

    if not sql:
        raise ValueError("Empty SQL statement")

    # Permit one optional trailing semicolon.
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()

    if ";" in sql:
        raise ValueError(
            "Multiple SQL statements are not allowed"
        )

    if not re.match(r"(?is)^SELECT\s", sql):
        raise ValueError(
            "Only SELECT statements are allowed"
        )

    forbidden = re.compile(
        r"\b("
        r"INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|"
        r"TRUNCATE|GRANT|REVOKE|CALL|EXEC|"
        r"INTO\s+OUTFILE|INTO\s+DUMPFILE"
        r")\b",
        re.IGNORECASE,
    )

    if forbidden.search(sql):
        raise ValueError(
            "Potentially unsafe SQL keyword detected"
        )

    if re.search(r"(?is)\bFOR\s+(UPDATE|SHARE)\b", sql):
        raise ValueError(
            "Locking SELECT statements are not permitted"
        )

    return rewrite_tables(sql)


# ---------------------------------------------------------
# 6. MySQL connection
# ---------------------------------------------------------

def connect_mysql():

    required = [
        "AIMIGRATE_MYSQL_HOST",
        "AIMIGRATE_MYSQL_PORT",
        "AIMIGRATE_MYSQL_DB",
        "AIMIGRATE_MYSQL_USER",
        "AIMIGRATE_MYSQL_PASSWORD",
    ]

    missing = [
        name for name in required
        if not os.getenv(name)
    ]

    if missing:
        raise RuntimeError(
            "Missing MySQL settings: "
            + ", ".join(missing)
        )

    return mysql.connector.connect(
        host=os.environ["AIMIGRATE_MYSQL_HOST"],
        port=int(os.environ["AIMIGRATE_MYSQL_PORT"]),
        database=os.environ["AIMIGRATE_MYSQL_DB"],
        user=os.environ["AIMIGRATE_MYSQL_USER"],
        password=os.environ["AIMIGRATE_MYSQL_PASSWORD"],
        ssl_ca="certs/mysql-ca.pem",
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        connection_timeout=10,
    )


# ---------------------------------------------------------
# 7. PostgreSQL connection
# ---------------------------------------------------------

def connect_postgres():

    required = [
        "AIMIGRATE_PG_HOST",
        "AIMIGRATE_PG_PORT",
        "AIMIGRATE_PG_DB",
        "AIMIGRATE_PG_USER",
        "AIMIGRATE_PG_PASSWORD",
    ]

    missing = [
        name for name in required
        if not os.getenv(name)
    ]

    if missing:
        raise RuntimeError(
            "Missing PostgreSQL settings: "
            + ", ".join(missing)
        )

    return psycopg.connect(
        host=os.environ["AIMIGRATE_PG_HOST"],
        port=int(os.environ["AIMIGRATE_PG_PORT"]),
        dbname=os.environ["AIMIGRATE_PG_DB"],
        user=os.environ["AIMIGRATE_PG_USER"],
        password=os.environ["AIMIGRATE_PG_PASSWORD"],
        sslmode="verify-full",
        sslrootcert="certs/postgres-ca.pem",
        connect_timeout=10,
        autocommit=True,
    )


# ---------------------------------------------------------
# 8. Create identical synthetic benchmark datasets
# ---------------------------------------------------------

def seed_databases(mysql_conn, pg_conn):
    """
    Create isolated tables and insert identical synthetic rows.

    Only AIMigrate-specific tables are modified.
    """

    # MySQL tables

    with mysql_conn.cursor() as cur:

        cur.execute("""
            CREATE TABLE IF NOT EXISTS aimigrate_bench_customers (
                customer_id INT PRIMARY KEY,
                customer_name VARCHAR(100) NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS aimigrate_bench_employees (
                employee_id INT PRIMARY KEY,
                first_name VARCHAR(100) NULL,
                last_name VARCHAR(100) NULL
            )
        """)

        cur.execute(
            "DELETE FROM aimigrate_bench_customers"
        )

        cur.execute(
            "DELETE FROM aimigrate_bench_employees"
        )

        cur.executemany(
            "INSERT INTO aimigrate_bench_customers VALUES (%s, %s)",
            CUSTOMERS,
        )

        cur.executemany(
            "INSERT INTO aimigrate_bench_employees VALUES (%s, %s, %s)",
            EMPLOYEES,
        )

    mysql_conn.commit()

    # PostgreSQL tables

    with pg_conn.cursor() as cur:

        cur.execute("""
            CREATE TABLE IF NOT EXISTS aimigrate_bench_customers (
                customer_id INTEGER PRIMARY KEY,
                customer_name VARCHAR(100) NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS aimigrate_bench_employees (
                employee_id INTEGER PRIMARY KEY,
                first_name VARCHAR(100) NULL,
                last_name VARCHAR(100) NULL
            )
        """)

        cur.execute(
            "DELETE FROM aimigrate_bench_customers"
        )

        cur.execute(
            "DELETE FROM aimigrate_bench_employees"
        )

        cur.executemany(
            "INSERT INTO aimigrate_bench_customers VALUES (%s, %s)",
            CUSTOMERS,
        )

        cur.executemany(
            "INSERT INTO aimigrate_bench_employees VALUES (%s, %s, %s)",
            EMPLOYEES,
        )


# ---------------------------------------------------------
# 9. Main experiment
# ---------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description=(
            "AIMigrate-Bench Phase 4C: "
            "Live cross-database semantic evaluation"
        )
    )

    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(
            "benchmarks/cases/extended.json"
        ),
    )

    parser.add_argument(
        "--observations",
        type=Path,
        default=Path(
            "results/phase31_gemini/observations.csv"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/phase4c"),
    )

    args = parser.parse_args()

    # Load benchmark cases.

    cases_bytes = args.cases.read_bytes()
    cases = json.loads(cases_bytes)

    if not isinstance(cases, list) or not cases:
        parser.error("Cases must be a nonempty JSON list")

    # Load Phase 3 observations.

    with args.observations.open(
        newline="",
        encoding="utf-8",
    ) as f:

        observations = list(
            csv.DictReader(f)
        )

    observation_map = {
        (row["case_id"], row["method"]): row
        for row in observations
    }

    mysql_conn = None
    pg_conn = None

    records = []

    try:

        print("\nConnecting to MySQL...")

        mysql_conn = connect_mysql()

        print("MySQL connected successfully.")

        print("\nConnecting to PostgreSQL...")

        pg_conn = connect_postgres()

        print("PostgreSQL connected successfully.")

        # Prepare controlled datasets.

        print("\nPreparing synthetic benchmark datasets...")

        seed_databases(mysql_conn, pg_conn)

        print("Synthetic datasets created successfully.")

        with mysql_conn.cursor() as mysql_cur, \
             pg_conn.cursor() as pg_cur:

            pg_cur.execute(
                "SET statement_timeout = 10000"
            )

            # Only MySQL -> PostgreSQL cases are evaluated.
            for case in cases:

                if (
                    case.get("source") != "mysql"
                    or case.get("target") != "postgres"
                ):
                    continue

                case_id = case["id"]

                print(
                    f"\nProcessing case: {case_id}"
                )

                # Execute original MySQL SQL once.

                source_rows = None
                source_error = ""

                try:

                    source_sql = validate_select(
                        case["sql"]
                    )

                    mysql_cur.execute(source_sql)

                    source_rows = mysql_cur.fetchall()

                except Exception as exc:

                    source_error = (
                        f"{type(exc).__name__}: {exc}"
                    )

                # Evaluate each migration method.

                for method in (
                    "rule",
                    "llm",
                    "hybrid",
                ):

                    item = observation_map.get(
                        (case_id, method)
                    )

                    api_calls = (
                        int(item.get("api_calls") or 0)
                        if item else 0
                    )

                    generated_sql = (
                        item.get("output_sql", "").strip()
                        if item else ""
                    )

                    record = {
                        "case_id": case_id,
                        "method": method,
                        "source_dialect": "mysql",
                        "target_dialect": "postgres",
                        "source_executed": source_rows is not None,
                        "target_executed": False,
                        "equivalent": False,
                        "source_row_count": (
                            len(source_rows)
                            if source_rows is not None
                            else None
                        ),
                        "target_row_count": None,
                        "api_calls": api_calls,
                        "duration_ms": None,
                        "translation_sql": generated_sql,
                        "error": "",
                    }

                    if source_error:

                        record["error"] = (
                            "Source execution failed: "
                            + source_error
                        )

                    elif not generated_sql:

                        record["error"] = (
                            item.get("error", "")
                            if item
                            else "No Phase 3 observation"
                        ) or "No generated SQL"

                    else:

                        try:

                            target_sql = validate_select(
                                generated_sql
                            )

                            start = time.perf_counter()

                            pg_cur.execute(target_sql)

                            target_rows = pg_cur.fetchall()

                            duration = (
                                time.perf_counter() - start
                            ) * 1000

                            record.update(
                                target_executed=True,
                                target_row_count=len(target_rows),
                                duration_ms=round(
                                    duration, 3
                                ),
                                equivalent=rows_equal(
                                    source_rows,
                                    target_rows,
                                    ordered=case.get(
                                        "ordered", False
                                    ),
                                ),
                            )

                        except Exception as exc:

                            record["error"] = (
                                f"{type(exc).__name__}: {exc}"
                            )

                    records.append(record)

                    print(
                        f"{case_id} | {method} | "
                        f"executed={record['target_executed']} | "
                        f"equivalent={record['equivalent']} | "
                        f"error={record['error'][:90]}"
                    )

    finally:

        if mysql_conn is not None:
            mysql_conn.close()

        if pg_conn is not None:
            pg_conn.close()

    # -----------------------------------------------------
    # 10. Save results
    # -----------------------------------------------------

    args.output.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        args.output / "observations.json"
    )

    csv_path = (
        args.output / "observations.csv"
    )

    json_path.write_text(
        json.dumps(records, indent=2),
        encoding="utf-8",
    )

    if records:

        with csv_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=list(records[0].keys()),
            )

            writer.writeheader()
            writer.writerows(records)

    # -----------------------------------------------------
    # 11. Generate method summary
    # -----------------------------------------------------

    summary = {}

    for method in (
        "rule",
        "llm",
        "hybrid",
    ):

        subset = [
            r for r in records
            if r["method"] == method
        ]

        executed = [
            r for r in subset
            if r["target_executed"]
        ]

        summary[method] = {
            "total_cases": len(subset),
            "target_executed": len(executed),
            "equivalent_cases": sum(
                r["equivalent"]
                for r in executed
            ),
            "api_calls": sum(
                r["api_calls"]
                for r in subset
            ),
            "execution_errors": sum(
                bool(r["error"])
                for r in subset
            ),
        }

    metadata = {
        "experiment": "AIMigrate-Bench Phase 4C",
        "source_engine": "MySQL",
        "target_engine": "PostgreSQL",
        "source_version": "8.4.11 (previously observed)",
        "target_version": "18.6 (previously observed)",
        "cases_sha256": hashlib.sha256(
            cases_bytes
        ).hexdigest(),
        "synthetic_rows": {
            "customers": len(CUSTOMERS),
            "employees": len(EMPLOYEES),
        },
        "comparison": (
            "Executed result comparison using synthetic data"
        ),
        "summary": summary,
        "semantic_equivalence_scope": (
            "Finite tested inputs and datasets only; "
            "not proof of universal equivalence."
        ),
    }

    (
        args.output / "metadata.json"
    ).write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("\n======================================")
    print("PHASE 4C EXPERIMENT COMPLETE")
    print("======================================")

    print(
        f"Total comparisons: {len(records)}"
    )

    print(
        f"Results saved to: {args.output}"
    )

    for method, stats in summary.items():

        print(
            f"{method}: "
            f"{stats['equivalent_cases']}/"
            f"{stats['target_executed']} equivalent; "
            f"{stats['execution_errors']} errors"
        )

    print(
        "\nEquivalence applies only to tested inputs "
        "and synthetic datasets."
    )


# ---------------------------------------------------------
# 12. Entry point
# ---------------------------------------------------------

if __name__ == "__main__":
    main()
