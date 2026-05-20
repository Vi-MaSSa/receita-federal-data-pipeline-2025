# Architecture — Receita Federal 2025 Pipeline

## Overview

This pipeline implements a **RAW → SILVER → GOLD** ETL/ELT architecture for Brazilian logistics company data enrichment using Receita Federal (RFB) establishment records combined with IBGE geographic references.

## Data Layers

### RAW (Bronze)

- **Source**: Receita Federal ZIPs (~1.5 GB/month)
- **Format**: CSV (latin1, semicolon-delimited, no header)
- **Columns**: 30 (RFB standard layout)
- **Storage**: Local (`dados_brutos/`) or S3 (`raw/receita_federal/...`)
- **Processing**: No transformation

### SILVER (Transformed)

- **Processor**: `scripts/transformer/service.py` (Polars LazyFrame)
- **Operations**:
  1. Extract & decompress ZIPs
  2. Read CSVs with encoding fallback (latin1 → utf-8)
  3. Filter: `situacao_cadastral == "02"` (active only)
  4. Filter: CNAE must match 11 logistics codes (principal OR secondary)
  5. Normalize: UTF-8 cast, whitespace removal
  6. Select: 6 columns (cnpj_basico, cnae_principal, cnae_secundario, cod_mun_rfb, etc.)
- **Output**: Polars DataFrame (in-memory, not persisted)
- **Efficiency**: Streaming LazyFrame handles 100+ GB without OOM

### GOLD (Enriched & Final)

- **Processor**: `scripts/warehouse/manager.py` (DuckDB)
- **Operations**:
  1. **Geographic Enrichment**:
     - Join with Municipios.csv (RFB reference) via cod_mun_rfb
     - Join with IBGE reference data (areas_ibge_2025.xls) via municipality name
     - Handle geographic exceptions (UF='EX' → NULL CODIGO_IBGE)
  2. **Deduplication**: GROUP BY CNPJ, keep 1 record per unique CNPJ
  3. **Validation**: Schema check, NULL enforcement, CNAE verification
- **Final Schema** (7 columns):
  - CNPJ_COMPLETO, CNAE_PRINCIPAL, CNAE_SECUNDARIO
  - UF, NOME_MUNICIPIO, CODIGO_IBGE_7, MES_COMPETENCIA
- **Output**: Parquet (primary) + CSV sample (100 rows) + Excel summary (charts)
- **Storage**:
  - Local: `output/receita_federal_2025.parquet`
  - S3: `s3://bucket/gold/receita_federal/.../ano=2025/mes={mes}/`

## Technology Stack

### Processing

- **Polars 0.x**: Lazy streaming CSV read from ZIPs (efficient for bandwidth-limited scenarios)
- **DuckDB**: In-memory OLAP for joins, aggregations, SQL exports

### Storage & Access

- **Boto3**: S3 data lake integration (ZIPs, references, outputs)
- **Python-Calamine**: Native Excel read (IBGE reference data)

### Data Science

- **MotherDuck** (optional): Hybrid local/cloud DuckDB with token-based auth

### Consumption

- **Parquet**: Open format, compression, compatible with Pandas, Polars, Spark
- **Excel/Power BI**: Pivot tables, charts on Gold data

## Execution Modes

### Local (Dry Run / Development)

```bash
python -m scripts.main --raw-path dados_brutos/2025-01
# Input: 1 month (~15 GB)
# RAM: ~2 GB peak
# Time: ~9 minutes
# Streaming ensures constant memory usage
```

### Local (Full Year / Pre-Production)

```bash
python -m scripts.main --raw-path dados_brutos/2025
# Input: 12 months (~150 GB)
# RAM: ~2 GB peak (streaming)
# Temp: ~50 GB (DuckDB spill-to-disk)
# Time: ~90 minutes
```

### Cloud (AWS S3 + MotherDuck)

```bash
export ENV=aws
export MOTHERDUCK_TOKEN=your_token
python -m scripts.main
# Automatically reads: s3://bucket/raw/receita_federal/.../ano=2025/mes=*/
# Outputs to: s3://bucket/gold/receita_federal/.../ano=2025/mes=*/
# Query results in MotherDuck console
```

## Data Flow Diagram

```
┌─────────────────────────────────┐
│ RAW (Bronze)                     │
│ RFB ZIPs (30 columns, latin1)   │
└──────────────┬──────────────────┘
               │ [CNPJTransformer]
               │ • Decompress
               │ • Read CSV (encoding fallback)
               │ • Filter: CNAE + Situacao='02'
               │ • Cast UTF-8, normalize
               ▼
┌──────────────────────────────────┐
│ SILVER (Transformed)             │
│ 6 columns, filtered records      │
│ ~7.9% match rate (2.2M from 28M) │
└──────────────┬───────────────────┘
               │ [WarehouseManager]
               │ • Join RFB Municipios
               │ • Join IBGE reference
               │ • Handle exceptions (UF='EX')
               ▼
┌──────────────────────────────────┐
│ GOLD (Enriched)                  │
│ 7 columns with geography          │
│ 184,320 records (1 month)         │
└──────────────┬───────────────────┘
               │ [WarehouseManager]
               │ • Deduplicate by CNPJ
               │ • Validate schema
               ▼
┌──────────────────────────────────┐
│ FINAL (Analytics-Ready)          │
│ Parquet + CSV sample + Excel     │
│ 151,283 unique CNPJs (1 month)   │
└──────────────────────────────────┘
```

## Performance Characteristics

| Operation              | Duration    | Memory     | Notes                            |
| ---------------------- | ----------- | ---------- | -------------------------------- |
| Polars read (1 month)  | ~5 min      | < 2 GB     | Streaming, LazyFrame             |
| DuckDB join + enrich   | ~2 min      | < 1 GB     | In-memory :memory: or MotherDuck |
| Deduplication          | ~1 min      | < 500 MB   | GROUP BY CNPJ                    |
| Export (Parquet + CSV) | ~1 min      | < 500 MB   | Parallel writers                 |
| **Total (1 month)**    | **~9 min**  | **< 2 GB** | All stages streaming             |
| **Total (12 months)**  | **~90 min** | **< 3 GB** | Constant memory (streaming)      |

## Error Handling

- **BadZipFile**: Logged as WARNING, skip to next file
- **Encoding issues**: Fallback latin1 → utf-8
- **Missing columns**: Validate min_colunas requirement, skip file
- **Join failures**: Geographic exception mapping (UF='EX' → NULL CODIGO_IBGE)
- **No matching CNAE**: Return empty Silver, log warning

## Tuning for Scale

### Large Data (100+ GB)

```bash
export DUCKDB_MAX_MEMORY=16GB
export DUCKDB_THREADS=8
python -m scripts.main --raw-path s3://bucket/raw/.../ano=2025/
```

### Memory-Constrained Machines

```bash
export DUCKDB_TEMP_DIR=/mnt/nvme/duckdb_temp  # Fast SSD spill-to-disk
python -m scripts.main --raw-path dados_brutos/2025-01  # 1 month at a time
```

## Monitoring & Observability

- **Logging**: stdout + file (`logs/pipeline_YYYYMMDD_HHMMSS.log`)
- **Metrics**: Stage counters (Bronze → Silver → Gold records)
- **Audit**: CSV sample (100 rows) for visual validation
- **Charts**: Excel summary (distributions by CNAE, UF)
