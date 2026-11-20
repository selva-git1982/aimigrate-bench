# AIMigrate-Bench (research prototype v0.1)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24405804.svg)](https://doi.org/10

A reproducible research benchmark for evaluating SQL-dialect translation methods in heterogeneous database migration. This is not a production migration tool. It supports rule-based translation, LLM and hybrid methods, cross-database execution checks (MySQL → PostgreSQL) on synthetic fixtures, and execution-triggered LLM repair (Phase 6). Equivalence results hold only for the included fixtures and engine versions.

## Install and run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e '.[test]'
pytest -q
aimigrate --methods rule
```

Results are written to `results/results.csv`, `results/results.json`, and `results/run_metadata.json`.

## Optional real LLM experiments

```bash
pip install -e '.[ai,test]'
export OPENAI_API_KEY='YOUR_KEY'  # never commit API keys
export AIMIGRATE_MODEL='gpt-4.1-mini'
aimigrate --methods rule llm hybrid
```

LLM experiments incur API costs and require model access. The `hybrid` implementation is an **initial parsing-guided fallback**, not a complete semantic repair system. The benchmark does not fake AI output when no API key is provided.

## Interpreting metrics

- `parsed`: the generated SQL was accepted by the sqlglot parser; it may still fail in a real DB.
- `exact_match`: normalized textual match to an optional expected string. Different but equivalent SQL may be marked false; matching text does not prove semantic correctness.
- `duration_ms`: wall-clock conversion time on the running machine.
- `input_tokens` and `output_tokens`: recorded when returned by the model API.

Do **not** publish these smoke-test values as claims of migration accuracy. Real semantic evaluation requires isolated source/target database execution, paired datasets, output and side-effect comparison, and human review of ambiguous cases.

## Roadmap for a publishable study

1. Add Docker-backed PostgreSQL/MySQL/SQL Server test environments, with documented image versions and licenses.
2. Build a diverse benchmark with stratified SQL object types and source-target pairs, avoiding leakage into prompts.
3. Execute generated statements on target engines and compare behavior against source engines using matched synthetic fixtures.
4. Implement bounded validation-feedback repair with per-attempt logs and failure taxonomy.
5. Benchmark conventional vendor tools and standalone LLMs under comparable conditions.
6. Run repeated trials, report confidence intervals, token cost, correctness, latency, and failure cases.
7. Freeze a Git commit, release datasets/scripts, and update the paper with **measured** findings.

## Research integrity

Never upload proprietary schemas, personal data, credentials, or production database content to third-party model APIs without authorization. Use synthetic fixtures. Record model names, versions, prompts, configurations, timestamps, and failures. Cite third-party tools and prior research. A code repository alone does not establish scientific novelty.

## GitHub publishing

Create an empty GitHub repository named `aimigrate-bench`, then in this directory:

```bash
git init
git add .
git commit -m "Initial reproducible migration benchmark"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/aimigrate-bench.git
git push -u origin main
```
