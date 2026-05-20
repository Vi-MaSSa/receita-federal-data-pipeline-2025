# Legacy Code Archive

## Purpose

This directory contains **temporary diagnostic scripts, deprecated utilities, and archived experimental code** that are **not part of the official production pipeline**.

Files here are preserved for:

- **Traceability**: Maintaining historical context of investigations and experiments.
- **Safety**: Keeping code that may be needed for emergency diagnostics or data archaeology.
- **Governance**: Making explicit what is legacy vs. production.

## Structure

- **`tmp/`**: Temporary scripts used during development and troubleshooting.
  - `__tmp_diag_nulls_gold_2025_01.py` — Investigation of NULL values in Gold layer (Jan 2025).
  - `__tmp_extract_ibge_exceptions.py` — IBGE data exception extraction experiment.
  - `__tmp_gold_test_2025_01.py` — Gold layer test variant.
  - `__tmp_investigar_nulls_gold_2025_01_ec2.py` — EC2 environment NULL investigation.
  - `__tmp_validate_exceptions.py` — Exception validation utility.

- **`tests/`**: Reserved for future test utilities (currently empty; scripts_02 and top-level validators not yet moved).

## Important Notes

1. **Not an entrypoint**: Never execute scripts in this directory as main pipeline entry.
2. **Import carefully**: These scripts may have stale imports or depend on deprecated patterns.
3. **No guarantees**: No maintenance commitment for legacy code. Use at own risk.
4. **Staging area**: This is a controlled consolidation phase; more legacy code may be moved here in future reorganization.

## What's NOT Here (Yet)

- `scripts_02/` — Alternative legacy pipeline (not moved in this phase).
- Top-level validators (`test_regex.py`, `validaEmpty.py`, etc.) — Consolidated in future phases.

## Next Steps

The production pipeline entrypoint remains:

```bash
python -m scripts.main
```

For questions about data lineage or historical decisions, see this directory's contents and associated git blame/history.
