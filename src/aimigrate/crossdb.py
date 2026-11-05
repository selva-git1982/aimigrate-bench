
"""Read-only cross-engine result comparison for controlled SELECT benchmarks.

Connects to MySQL and PostgreSQL using environment variables.
Requires mysql-connector-python and psycopg[binary].

Uses TLS certificate verification. Only executes single SELECT statements.
Never uses production data.
"""

import argparse
import collections
import json
import os
import time
from decimal import Decimal
from pathlib import Path

import mysql.connector
import psycopg


def normalize(value):
    """Normalize database values for cross-engine comparison."""
    if isinstance(value, Decimal):
        return ("number", str(value.normalize()))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return ("number", str(Decimal(str(value)).normalize()))

    if value is None:
        return ("null",)

    if isinstance(value, (bytes, bytearray)):
        return ("bytes", bytes(value).hex())

    return (type(value).__name__, str(value))


def normalize_rows(rows):
    return [tuple(normalize(value) for value in row) for row in rows]


def compare_rows(source, target, ordered=False):
    """Compare result sets, preserving duplicates."""
    left = normalize_rows(source)
    right = normalize_rows(target)

    if ordered:
        return left == right

    return collections.Counter(left) == collections.Counter(right)


def validate_select(sql):
    """Restrict benchmark statements to a single SELECT."""
    statement = sql.strip()

    if not statement:
        raise ValueError("Empty SQL statement")

    # Permit one optional trailing semicolon.
    if statement.endswith(";"):
        statement = statement[:-1].rstrip()

    if ";" in statement:
        raise ValueError("Multiple SQL statements are not allowed")

    if not statement.upper().startswith("SELECT "):
        raise ValueError("Only SELECT statements are allowed")

    return statement


def connect_mysql():
    required = [
        "AIMIGRATE_MYSQL_HOST",
        "AIMIGRATE_MYSQL_PORT",
        "AIMIGRATE_MYSQL_DB",
        "AIMIGRATE_MYSQL_USER",
        "AIMIGRATE_MYSQL_PASSWORD",
    ]

    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing MySQL environment variables: " + ", ".join(missing)
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


def connect_postgres():
    required = [
        "AIMIGRATE_PG_HOST",
        "AIMIGRATE_PG_PORT",
        "AIMIGRATE_PG_DB",
        "AIMIGRATE_PG_USER",
        "AIMIGRATE_PG_PASSWORD",
    ]

    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing PostgreSQL environment variables: " + ", ".join(missing)
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
    )


def run():
    parser = argparse.ArgumentParser(
        description="Compare read-only MySQL and PostgreSQL SELECT results"
    )

    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("benchmarks/crossdb/mysql_postgres.json"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/phase4b"),
    )

    args = parser.parse_args()

    cases_bytes = args.cases.read_bytes()
    cases = json.loads(cases_bytes)

    if not isinstance(cases, list) or not cases:
        parser.error("Cases must be a nonempty JSON list")

    mysql_conn = None
    pg_conn = None
    observations = []

    try:
        print("Connecting to MySQL...")
        mysql_conn = connect_mysql()
        print("MySQL connection successful.")

        print("Connecting to PostgreSQL...")
        pg_conn = connect_postgres()
        print("PostgreSQL connection successful.")

        with mysql_conn.cursor() as mysql_cur, pg_conn.cursor() as pg_cur:

            # Prevent long-running PostgreSQL benchmark queries.
            pg_cur.execute("SET statement_timeout = 10000")

            for case in cases:
                record = {
                    "id": case["id"],
                    "source_engine": "mysql",
                    "target_engine": "postgresql",
                    "equivalent": False,
                    "source_rows": None,
                    "target_rows": None,
                    "duration_ms": None,
                    "error": "",
                }

                start = time.perf_counter()

                try:
                    source_sql = validate_select(case["source_sql"])
                    target_sql = validate_select(case["target_sql"])

                    mysql_cur.execute(source_sql)
                    source_rows = mysql_cur.fetchall()

                    pg_cur.execute(target_sql)
                    target_rows = pg_cur.fetchall()

                    equivalent = compare_rows(
                        source_rows,
                        target_rows,
                        ordered=case.get("ordered", False),
                    )

                    record.update(
                        equivalent=equivalent,
                        source_rows=len(source_rows),
                        target_rows=len(target_rows),
                    )

                except Exception as exc:
                    record["error"] = (
                        f"{type(exc).__name__}: {exc}"
                    )

                    # Recover the PostgreSQL transaction if needed.
                    if pg_conn is not None:
                        pg_conn.rollback()

                record["duration_ms"] = round(
                    (time.perf_counter() - start) * 1000, 3
                )

                observations.append(record)

                print(
                    f"{case['id']}: "
                    f"equivalent={record['equivalent']} "
                    f"source_rows={record['source_rows']} "
                    f"target_rows={record['target_rows']} "
                    f"duration_ms={record['duration_ms']} "
                    f"error={record['error'][:100]}"
                )

    finally:
        if mysql_conn is not None:
            mysql_conn.close()

        if pg_conn is not None:
            pg_conn.close()

    args.output.mkdir(parents=True, exist_ok=True)

    (args.output / "observations.json").write_text(
        json.dumps(observations, indent=2),
        encoding="utf-8",
    )

    metadata = {
        "source_engine": "MySQL",
        "target_engine": "PostgreSQL",
        "case_count": len(cases),
        "successful_comparisons": sum(
            not item["error"] for item in observations
        ),
        "equivalent_cases": sum(
            item["equivalent"] for item in observations
        ),
        "cases_sha256": __import__("hashlib").sha256(
            cases_bytes
        ).hexdigest(),
        "comparison_type": "executed_result_comparison",
        "production_data_used": False,
    }

    (args.output / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print(
        f"\nWrote {len(observations)} comparisons to {args.output}."
    )
    print(
        "Equivalence applies only to the tested inputs and datasets."
    )


if __name__ == "__main__":
    run()
