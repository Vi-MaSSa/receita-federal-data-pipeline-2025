# Receita Federal 2025 — Logistics Establishment Pipeline

A professional ETL/ELT pipeline for processing Brazilian Receita Federal (RFB) establishment data with geographic enrichment (IBGE) for 11 logistics business codes.

**Status**: Production (Local + AWS Graviton3)  
**Year**: 2025  
**Focus**: Logistics (Transportes, Depósitos, Operadores Logísticos)

---

## Quick Start

```bash
# 1. Setup environment
python -m venv venv_dados
source venv_dados/bin/activate  # or .\venv_dados\Scripts\activate on Windows
pip install -r requirements.txt

# 2. Configure
cp .env.example .env

# 3. Run (dry run — 1 month)
python -m scripts.main --raw-path dados_brutos/2025-01

# ✓ Check output/
```

---

## Overview

### Architecture: RAW → SILVER → GOLD

```
RAW (Bronze)
  ↓ [Polars: decompress ZIP, filter CNAE, filter Situacao='02', UTF-8 cast]
SILVER (Transformed)
  ↓ [DuckDB: join RFB Municipios, join IBGE, handle exceptions]
GOLD (Enriched & Deduplicated)
  ↓ [Export: Parquet + CSV sample + Excel summary]
Final Output (Analytics-Ready)
```

**Efficiency**:

- Streaming: Handles 100+ GB with 2 GB RAM
- Processing: 1 month (~9 min), 12 months (~90 min)
- Deduplication: ~18% records removed (same CNPJ, multiple updates)

---

## Technologies

- **Python 3.10+**
- **Polars 0.x** — Lazy streaming CSV read from ZIPs
- **DuckDB** — In-memory OLAP SQL engine
- **Boto3** — S3 integration (data lake)
- **Python-Calamine** — Native Excel read (IBGE data)
- **MotherDuck** (optional) — Cloud analytics

---

## Entrypoint: `python -m scripts.main`

### Single Month (Dry Run)

```bash
python -m scripts.main --raw-path dados_brutos/2025-01
# ✓ output/receita_federal_2025_jan.parquet (~125 MB)
# ✓ output/resumo_2025_jan.xlsx (charts, distributions)
# ✓ output/amostra_100linhas.csv (validation sample)
```

### Full Year

```bash
python -m scripts.main --raw-path dados_brutos/2025
# ✓ output/receita_federal_2025.parquet (~1.5 GB, 1.2M unique CNPJs)
```

### AWS S3

```bash
export ENV=aws
export S3_BUCKET=your-bucket-name
python -m scripts.main
# Reads from: s3://bucket/raw/receita_federal/.../ano=2025/mes=*/
# Outputs to: s3://bucket/gold/receita_federal/.../ano=2025/mes=*/
```

### With MotherDuck (Analytics)

```bash
export MOTHERDUCK_TOKEN=your_token
python -m scripts.main --raw-path dados_brutos/2025-01
# Use MotherDuck Web Console to query results
```

---

## Business Rules (Immutable)

### CNAE Filters (11 Logistics Codes)

- **Primary**: Transportes (52.11), Depósitos (52.50), Operadores (53.10), Especializados (53.20), Urbano (49.30)
- **Codes**: 5211701, 5211702, 5211799, 5250801–04, 5310501, 5320201–02, 4930201
- **Matching**: CNAE_PRINCIPAL OR CNAE_SECUNDARIO (multi-value field)
- **Impact**: ~7.9% match rate (2.2M from 28M RFB records)

### Status Filter

- **Only Active**: `situacao_cadastral == "02"` (active establishments)
- **Exclusions**: All inactive codes (suspended, cancelled, etc.)
- **Impact**: ~30% records filtered out

### Geographic Enrichment

- **Join 1**: RFB reference (Municipios.csv) via cod_mun_rfb
- **Join 2**: IBGE reference (areas_ibge_2025.xls) via municipality name
- **Exception**: UF='EX' (Exterior) → CODIGO_IBGE=NULL (by design, 184 records)

### Final Schema (7 Columns, Immutable)

| Column          | Type        | Notes                         |
| --------------- | ----------- | ----------------------------- |
| CNPJ_COMPLETO   | VARCHAR(14) | Primary key, unique per dedup |
| CNAE_PRINCIPAL  | VARCHAR(7)  | Always in 11-code whitelist   |
| CNAE_SECUNDARIO | VARCHAR     | Null ok; CSV if present       |
| UF              | VARCHAR(2)  | 27 states + 'EX'              |
| NOME_MUNICIPIO  | VARCHAR     | Normalized, uppercase         |
| CODIGO_IBGE_7   | INT         | Null for UF='EX' or join fail |
| MES_COMPETENCIA | VARCHAR(7)  | Format: YYYY-MM               |

---

## Data Characteristics (2025 Annual Estimate)

| Metric                | Value               |
| --------------------- | ------------------- |
| Raw records (Bronze)  | 28.0M               |
| Match rate (Silver)   | 7.9% (2.2M)         |
| Post-dedup (Final)    | 1.2M unique CNPJs   |
| Output size (Parquet) | ~1.5 GB             |
| Top state (SP)        | 28% of records      |
| Exterior (EX)         | 184 records (0.01%) |

---

## Project Status

| Component                 | Status        | Notes                            |
| ------------------------- | ------------- | -------------------------------- |
| CNPJTransformer (Polars)  | ✅ Production | Streaming, efficient             |
| WarehouseManager (DuckDB) | ✅ Production | Join, dedup, export              |
| S3 Integration            | ✅ Production | Boto3, IAM role recommended      |
| MotherDuck (Analytics)    | ⚠️ Optional   | Token-based, no charge if unused |
| CLI / Entrypoints         | ✅ Production | `scripts/main.py` is canonical   |
| Tests                     | ⏳ Planned    | Smoke tests for CNAE, schema     |
| Documentation             | 🔄 Improving  | README + docs/ in progress       |

---

## ⚠️ Important: Large Data Not Versioned

This project processes **20+ GB of establishment data** that is **NOT tracked in Git**:

- **Raw ZIPs** (`dados_brutos/`): Downloaded from S3, never versioned
- **Outputs** (`output/`): Generated artifacts, never versioned
- **Logs** (`logs/`): Pipeline execution logs, never versioned

See `.gitignore` for complete list. Clone and run locally or on AWS; data is loaded on demand from S3 or local filesystem.

---

## Next Steps

1. **Install** → Follow [Execution Guide](docs/execution_guide.md)
2. **Understand** → Read [Architecture](docs/architecture.md) & [Business Rules](docs/business_rules.md)
3. **Run** → `python -m scripts.main --raw-path dados_brutos/2025-01`
4. **Validate** → Check `output/` and Excel summary
5. **Scale** → Process full year or migrate to AWS

---

## Documentation

- **[Architecture](docs/architecture.md)** — Data layers, processing flow, technology stack
- **[Business Rules](docs/business_rules.md)** — CNAE filters, schema, validation rules
- **[Execution Guide](docs/execution_guide.md)** — Installation, local/AWS/MotherDuck setup
- **[Data Dictionary](docs/data_dictionary.md)** — GOLD schema field definitions

---

## Contact

Linkedin: https://www.linkedin.com/in/vinicius01/
