"""Conversion, optional LLM translation, and transparent benchmark measurements."""
from __future__ import annotations
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
import sqlglot

DIALECTS = {"postgres": "postgres", "mysql": "mysql", "tsql": "tsql"}

@dataclass
class Result:
    case_id: str
    method: str
    source_dialect: str
    target_dialect: str
    output_sql: str
    parsed: bool
    exact_match: Optional[bool]
    duration_ms: float
    error: str = ""
    model: str = ""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


def parseable(sql: str, dialect: str) -> bool:
    try:
        if not sql.strip():
            return False
        statements = sqlglot.parse(sql, read=DIALECTS[dialect], error_level="RAISE")
        return bool(statements) and all(s is not None for s in statements)
    except Exception:
        return False


def rule_based(sql: str, source: str, target: str) -> str:
    return ";\n".join(s for s in sqlglot.transpile(sql, read=DIALECTS[source], write=DIALECTS[target], error_level="RAISE") if s)


def llm_translate(sql: str, source: str, target: str, diagnostics: str = "") -> tuple[str, str, Optional[int], Optional[int]]:
    """Requires explicit API configuration; never silently substitutes simulated AI."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")
    model = os.getenv("AIMIGRATE_MODEL", "gpt-4.1-mini")
    from openai import OpenAI
    prompt = (f"Convert SQL from {source} to {target}. Preserve semantics. "
              "Return only SQL without markdown. Do not invent tables or columns.\n"
              f"Diagnostic feedback: {diagnostics}\nSource SQL:\n{sql}")
    response = OpenAI().chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "system", "content": "You are a careful SQL dialect migration assistant."},
                  {"role": "user", "content": prompt}])
    content = (response.choices[0].message.content or "").strip()
    if content.startswith("```"):
        content = "\n".join(content.splitlines()[1:-1]).strip()
    usage = response.usage
    return content, model, getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)


def run_case(case: dict, method: str) -> Result:
    source, target = case["source"], case["target"]
    if source not in DIALECTS or target not in DIALECTS:
        raise ValueError("Unsupported dialect")
    start = time.perf_counter()
    output, err, model, in_tok, out_tok = "", "", "", None, None
    try:
        if method == "rule":
            output = rule_based(case["sql"], source, target)
        elif method == "llm":
            output, model, in_tok, out_tok = llm_translate(case["sql"], source, target)
        elif method == "hybrid":
            try:
                output = rule_based(case["sql"], source, target)
            except Exception as exc:
                output, model, in_tok, out_tok = llm_translate(case["sql"], source, target, str(exc))
            if not parseable(output, target):
                output, model, in_tok, out_tok = llm_translate(case["sql"], source, target, "Previous candidate failed target-dialect parsing: " + output)
        else:
            raise ValueError(f"Unknown method: {method}")
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    duration = (time.perf_counter() - start) * 1000
    parsed = parseable(output, target)
    # Exact SQL string equality is diagnostic only; NOT semantic equivalence.
    expected = case.get("expected_sql")
    exact = (" ".join(output.lower().split()) == " ".join(expected.lower().split())) if expected is not None else None
    return Result(case["id"], method, source, target, output, parsed, exact, round(duration, 3), err, model, in_tok, out_tok)


def run_suite(path: Path, methods: list[str]) -> list[Result]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case IDs")
    return [run_case(case, method) for case in cases for method in methods]
