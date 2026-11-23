# Synthetic healthcare benchmark extension (proposed; not yet executed)

Eight paired read-only SQL cases for patient visit windows, treatment duration, lab missingness, cohort eligibility, lab counts, NULL ordering, lab status, and date extraction. These are **not measured results**.

## Run
1. In disposable MySQL and PostgreSQL databases, execute the corresponding `*_fixture.sql` scripts.
2. Set the `AIMIGRATE_MYSQL_*` and `AIMIGRATE_PG_*` connection environment variables required by `src/aimigrate/crossdb.py`, with verified TLS certificates under `certs/`.
3. From repository root: `python -m aimigrate.crossdb --cases benchmarks/healthcare/healthcare_crossdb_cases.json --output results/healthcare`
4. Review every `observations.json` error and mismatch; report results only after both engines run.

The cases use hand-authored target SQL as reference checks; they do not measure SQLGlot or LLM translation accuracy. To measure translation accuracy, separately generate candidate target SQL with each method and compare those candidates to source results.

Date return types and driver normalization can create false mismatches even for clinically equivalent dates. The comparison policy should be declared before reporting pass rates. No real patient data are used.
