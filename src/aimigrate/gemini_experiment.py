"""Gemini experiments: baseline LLM vs rule-first, parse-feedback hybrid.

Static parsing is NOT database execution or semantic equivalence.

Features:
- Retry handling through aimigrate.retry.call_with_retries
- Hard API-attempt budget per invocation
- Atomic CSV/JSON/metadata checkpoint after every observation
- Explicit resume with configuration and benchmark-hash validation
- Optional retry of completed observations containing errors
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import sqlglot

from .engine import DIALECTS, rule_based
from .retry import call_with_retries
from .validator import validate_sql


PROMPT_VERSION = "phase3-v1"
OBSERVATION_FIELDS = list((
    "case_id",
    "method",
    "source_dialect",
    "target_dialect",
    "model",
    "output_sql",
    "parsed",
    "reference_ast_match",
    "repair_attempted",
    "repair_accepted",
    "api_calls",
    "input_tokens",
    "output_tokens",
    "duration_ms",
    "error",
    "semantic_equivalence_verified",
    "database_execution_verified",
))


def clean_sql(text: str) -> str:
    text = (text or "").strip()
    match = re.fullmatch(
        r"```(?:sql)?\s*\n?(.*?)\n?```",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else text


def prompt_for(
    sql: str,
    source: str,
    target: str,
    candidate: str = "",
    diagnostic: str = "",
) -> str:
    context = (
        f"Previous target SQL:\n{candidate}\n"
        f"Parser diagnostic:\n{diagnostic}\n"
        if candidate or diagnostic
        else ""
    )
    return (
        f"Translate the following {source} SQL into {target} SQL. "
        "Preserve behavior including NULL handling and ordering. "
        "Do not invent tables or columns. Return only SQL, no explanation "
        "or markdown. Never execute the SQL.\n"
        + context
        + "Source SQL:\n"
        + sql
    )


def gemini_call(
    prompt: str,
    model: str,
    temperature: float = 0.0,
) -> tuple[str, int | None, int | None]:
    """SDK is imported lazily so unit tests need no network/API key."""
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is missing; set it in the current terminal"
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                candidate_count=1,
            ),
        )
        usage = getattr(response, "usage_metadata", None)
        return (
            clean_sql(response.text or ""),
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
        )
    finally:
        client.close()


@dataclass
class Observation:
    case_id: str
    method: str
    source_dialect: str
    target_dialect: str
    model: str
    output_sql: str
    parsed: bool
    reference_ast_match: bool | None
    repair_attempted: bool
    repair_accepted: bool
    api_calls: int
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: float
    error: str
    semantic_equivalence_verified: bool = False
    database_execution_verified: bool = False


def evaluate(
    case: dict,
    method: str,
    model: str,
    caller: Callable[
        [str, str, float],
        tuple[str, int | None, int | None],
    ] = gemini_call,
    temperature: float = 0.0,
    max_attempts: int = 1,
    before_api_call: Callable[[], None] | None = None,
) -> Observation:
    source, target = case["source"], case["target"]

    if source not in DIALECTS or target not in DIALECTS:
        raise ValueError("Unsupported dialect")
    if method not in ("rule", "llm", "hybrid"):
        raise ValueError("Unknown method")

    start = time.perf_counter()
    output, error = "", ""
    api_calls, in_tokens, out_tokens = 0, 0, 0
    repair_attempted = repair_accepted = False
    seen_usage = False

    def request(prompt: str) -> str:
        nonlocal api_calls, in_tokens, out_tokens, seen_usage

        def attempt() -> tuple[str, int | None, int | None]:
            return caller(prompt, model, temperature)

        def count_attempt() -> None:
            nonlocal api_calls
            # Budget is checked before each actual API attempt.
            if before_api_call is not None:
                before_api_call()
            api_calls += 1

        answer, input_count, output_count = call_with_retries(
            attempt,
            max_attempts=max_attempts,
            on_attempt=count_attempt,
        )

        if input_count is not None:
            in_tokens += input_count
            seen_usage = True
        if output_count is not None:
            out_tokens += output_count
            seen_usage = True

        return clean_sql(answer)

    try:
        if method == "rule":
            output = rule_based(case["sql"], source, target)

        elif method == "llm":
            output = request(prompt_for(case["sql"], source, target))

        else:
            diagnostic = ""
            try:
                output = rule_based(case["sql"], source, target)
            except Exception as exc:
                diagnostic = (
                    f"Rule conversion failed: {type(exc).__name__}: {exc}"
                )

            if not validate_sql(output, target).valid:
                repair_attempted = True
                output = request(
                    prompt_for(
                        case["sql"],
                        source,
                        target,
                        output,
                        diagnostic or "Target parse failed",
                    )
                )
                repair_accepted = validate_sql(output, target).valid

            # Do NOT repair a parse-valid query merely because reference differs.

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    validation = validate_sql(output, target, case.get("expected_sql"))

    return Observation(
        case_id=case["id"],
        method=method,
        source_dialect=source,
        target_dialect=target,
        model=model if api_calls else "",
        output_sql=output,
        parsed=validation.valid,
        reference_ast_match=validation.reference_ast_match,
        repair_attempted=repair_attempted,
        repair_accepted=repair_accepted,
        api_calls=api_calls,
        input_tokens=in_tokens if seen_usage else None,
        output_tokens=out_tokens if seen_usage else None,
        duration_ms=round((time.perf_counter() - start) * 1000, 3),
        error=error,
    )


def _atomic_write_text(path: Path, content: str) -> None:
    """Write a file atomically using a sibling temporary file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def save_checkpoint(
    output_dir: Path,
    observations: list[Observation],
    metadata: dict,
) -> None:
    """Atomically persist all observations and metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(item) for item in observations]

    _atomic_write_text(
        output_dir / "observations.json",
        json.dumps(rows, indent=2),
    )

    csv_path = output_dir / "observations.csv"
    csv_tmp = csv_path.with_name(csv_path.name + ".tmp")
    with csv_tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=OBSERVATION_FIELDS,
        )
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    csv_tmp.replace(csv_path)

    _atomic_write_text(
        output_dir / "metadata.json",
        json.dumps(metadata, indent=2),
    )


def _is_budget_interruption(observation: Observation) -> bool:
    """A budget interruption is pending work, not a completed model result."""
    return (
        "API call budget exhausted" in (observation.error or "")
    )


def _load_checkpoint(output_dir: Path) -> list[Observation]:
    json_path = output_dir / "observations.json"
    if not json_path.exists():
        return []

    raw = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Checkpoint observations.json must contain a list")

    loaded = []
    for row in raw:
        # Ignore unknown future fields, but require all current dataclass fields.
        allowed = set(Observation.__dataclass_fields__)
        filtered = {key: value for key, value in row.items() if key in allowed}
        missing = allowed - set(filtered)
        if missing:
            raise ValueError(
                "Checkpoint row is missing fields: "
                + ", ".join(sorted(missing))
            )
        loaded.append(Observation(**filtered))
    return loaded


def _metadata_for(
    args: argparse.Namespace,
    cases_sha256: str,
    cases_count: int,
    observations: list[Observation],
    status: str,
    invocation_api_calls: int,
) -> dict:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "model": args.model,
        "prompt_version": PROMPT_VERSION,
        "temperature": args.temperature,
        "methods": args.methods,
        "case_count": cases_count,
        "cases_sha256": cases_sha256,
        "python": sys.version,
        "platform": platform.platform(),
        "sqlglot_version": sqlglot.__version__,
        "total_api_calls_all_saved_observations": sum(
            item.api_calls for item in observations
        ),
        "api_calls_this_invocation": invocation_api_calls,
        "max_attempts": args.max_attempts,
        "max_calls_per_invocation": args.max_calls,
        "static_validation_only": True,
        "semantic_equivalence_verified": False,
        "database_execution_verified": False,
    }


def _validate_resume_metadata(
    metadata_path: Path,
    expected: dict,
) -> None:
    if not metadata_path.exists():
        raise ValueError(
            "Cannot safely resume: metadata.json is missing. "
            "Use a new output directory or restore the matching metadata."
        )

    previous = json.loads(metadata_path.read_text(encoding="utf-8"))
    keys = (
        "model",
        "prompt_version",
        "temperature",
        "methods",
        "case_count",
        "cases_sha256",
        "max_attempts",
    )
    mismatches = [
        key for key in keys
        if previous.get(key) != expected.get(key)
    ]
    if mismatches:
        raise ValueError(
            "Resume configuration does not match existing checkpoint: "
            + ", ".join(mismatches)
            + ". Use the original settings or a new --output directory."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Gemini AIMigrate experiments with checkpoint/resume"
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("benchmarks/cases/extended.json"),
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=["rule", "llm", "hybrid"],
        default=["rule"],
    )
    parser.add_argument(
        "--model",
        default=os.getenv(
            "AIMIGRATE_GEMINI_MODEL",
            "gemini-flash-latest",
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/gemini_phase3"),
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--max-calls",
        type=int,
        default=20,
        help="Maximum actual Gemini API attempts in this invocation, including retries",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum attempts per Gemini request, including the first call",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from observations.json after validating experiment configuration",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="With --resume, retry saved observations that contain an error",
    )

    args = parser.parse_args()

    if args.retry_errors and not args.resume:
        parser.error("--retry-errors requires --resume")
    if not 0 <= args.temperature <= 2:
        parser.error("temperature must be between 0 and 2")
    if args.max_calls < 0:
        parser.error("--max-calls must be nonnegative")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be >= 1")

    cases_bytes = args.cases.read_bytes()
    cases = json.loads(cases_bytes)

    if (
        not isinstance(cases, list)
        or not cases
        or len({case["id"] for case in cases}) != len(cases)
    ):
        parser.error("Cases must be a nonempty list with unique IDs")

    for case in cases:
        for required in ("id", "source", "target", "sql"):
            if required not in case:
                parser.error(f"Case is missing required field: {required}")

    cases_sha256 = hashlib.sha256(cases_bytes).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)

    checkpoint_json = args.output / "observations.json"
    checkpoint_csv = args.output / "observations.csv"
    metadata_path = args.output / "metadata.json"
    checkpoint_exists = (
        checkpoint_json.exists()
        or checkpoint_csv.exists()
        or metadata_path.exists()
    )

    if checkpoint_exists and not args.resume:
        parser.error(
            f"Output directory {args.output} already contains experiment files. "
            "Choose a new --output directory or use --resume."
        )

    if args.resume:
        observations = _load_checkpoint(args.output)
        expected_metadata = {
            "model": args.model,
            "prompt_version": PROMPT_VERSION,
            "temperature": args.temperature,
            "methods": args.methods,
            "case_count": len(cases),
            "cases_sha256": cases_sha256,
            "max_attempts": args.max_attempts,
        }
        _validate_resume_metadata(metadata_path, expected_metadata)
    else:
        observations = []

    # Ensure saved observations belong to requested case/method combinations.
    case_ids = {case["id"] for case in cases}
    method_set = set(args.methods)
    for item in observations:
        if item.case_id not in case_ids or item.method not in method_set:
            parser.error(
                "Checkpoint contains case/method entries not present in this run"
            )

    existing = {
        (item.case_id, item.method): item
        for item in observations
    }

    def should_skip(item: Observation | None) -> bool:
        if item is None:
            return False
        if _is_budget_interruption(item):
            return False
        if args.retry_errors and item.error:
            return False
        return True

    pending = [
        (case, method)
        for case in cases
        for method in args.methods
        if not should_skip(existing.get((case["id"], method)))
    ]

    needs_gemini = any(method in ("llm", "hybrid") for _, method in pending)
    if needs_gemini and not os.getenv("GEMINI_API_KEY"):
        parser.error(
            "GEMINI_API_KEY is not set (do not paste it into chat or source code)"
        )

    attempted_calls = 0
    status = "running"

    metadata = _metadata_for(
        args,
        cases_sha256,
        len(cases),
        observations,
        status,
        attempted_calls,
    )
    # Save an initial checkpoint/manifest before making API calls.
    save_checkpoint(args.output, observations, metadata)

    def enforce_budget() -> None:
        nonlocal attempted_calls
        if attempted_calls >= args.max_calls:
            raise RuntimeError("API call budget exhausted")
        attempted_calls += 1

    print(
        f"Starting experiment: {len(cases)} cases, "
        f"{len(args.methods)} methods, {len(pending)} pending observations."
    )
    print(
        f"API attempt budget for this invocation: {args.max_calls}; "
        f"retry attempts per request: {args.max_attempts}."
    )

    stop_experiment = False

    try:
        for case in cases:
            if stop_experiment:
                break

            for method in args.methods:
                key = (case["id"], method)
                previous = existing.get(key)

                if should_skip(previous):
                    continue

                # Conservative hybrid policy: don't begin a case that might
                # need a repair if no API budget remains.
                if method in ("llm", "hybrid") and attempted_calls >= args.max_calls:
                    print(
                        "API attempt budget exhausted; stopping cleanly "
                        "before the next API-capable observation."
                    )
                    stop_experiment = True
                    break

                result = evaluate(
                    case,
                    method,
                    args.model,
                    temperature=args.temperature,
                    max_attempts=args.max_attempts,
                    before_api_call=enforce_budget,
                )

                # Replace an earlier budget-interrupted/error observation if
                # this was an explicit retry; otherwise append a new result.
                if previous is not None:
                    observations = [
                        item for item in observations
                        if (item.case_id, item.method) != key
                    ]
                observations.append(result)
                existing[key] = result

                # Persist immediately after every completed observation.
                metadata = _metadata_for(
                    args,
                    cases_sha256,
                    len(cases),
                    observations,
                    "running",
                    attempted_calls,
                )
                save_checkpoint(args.output, observations, metadata)

                print(
                    f'{case["id"]}: {method} '
                    f'parsed={result.parsed} '
                    f'calls={result.api_calls} '
                    f'error={result.error[:120]}'
                )

                if _is_budget_interruption(result):
                    print(
                        "This observation was interrupted by the API budget. "
                        "It is checkpointed and will be eligible for resume."
                    )
                    stop_experiment = True
                    break

    except KeyboardInterrupt:
        status = "interrupted"
        print("\nInterrupted by user. Saving current checkpoint.")
        raise
    finally:
        if not stop_experiment and status == "running":
            # Determine whether every requested case/method has a saved result.
            unfinished = [
                (case["id"], method)
                for case in cases
                for method in args.methods
                if (
                    (case["id"], method) not in existing
                    or _is_budget_interruption(existing[(case["id"], method)])
                )
            ]
            status = "complete" if not unfinished else "incomplete"

        metadata = _metadata_for(
            args,
            cases_sha256,
            len(cases),
            observations,
            status,
            attempted_calls,
        )
        save_checkpoint(args.output, observations, metadata)

    total_expected = len(cases) * len(args.methods)
    saved_count = len(observations)

    print("\n========================================")
    print("AIMIGRATE EXPERIMENT CHECKPOINT")
    print("========================================")
    print(f"Saved observations: {saved_count}/{total_expected}")
    print(f"API attempts this invocation: {attempted_calls}")
    print(f"Status: {status}")
    print(f"Output directory: {args.output}")
    print("Static validation only; semantic equivalence NOT verified.")

    if status != "complete":
        print(
            "To continue later, rerun the same command with --resume. "
            "Previously completed observations will be skipped."
        )


if __name__ == "__main__":
    main()
