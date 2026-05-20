#!/usr/bin/env python3
"""Validate NULL count reduction after exception mapping."""
import duckdb

p = '/mnt/nvme_tmp/duckdb_temp/gold_test_2025_01.parquet'
con = duckdb.connect(':memory:')
con.execute(f"CREATE VIEW g AS SELECT * FROM read_parquet('{p}')")

total = con.execute('SELECT COUNT(*) FROM g').fetchone()[0]
nulls = con.execute(
    'SELECT COUNT(*) FILTER (WHERE NOME_MUNICIPIO IS NULL AND CODIGO_IBGE IS NULL) FROM g'
).fetchone()[0]
matched = total - nulls
pct_null = (nulls / total * 100) if total > 0 else 0.0
pct_matched = (matched / total * 100) if total > 0 else 0.0

print(f"=== VALIDATION RESULTS ===")
print(f"Total records: {total:,}")
print(f"Matched: {matched:,} ({pct_matched:.2f}%)")
print(f"NULL: {nulls:,} ({pct_null:.4f}%)")
print(f"Improvement target: <= 184 NULLs (EX only)")

if nulls <= 184:
    print("✓ SUCCESS: Exception mapping effective!")
else:
    print(f"⚠ ISSUE: Still have {nulls - 184} unexpected NULLs")
