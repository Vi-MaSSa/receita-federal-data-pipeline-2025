# Data Dictionary — GOLD Layer

## Schema Definition

The GOLD layer (final output) contains 7 columns with the following definition:

| #   | Column          | Type        | Null?    | PK? | Description                       | Example         |
| --- | --------------- | ----------- | -------- | --- | --------------------------------- | --------------- |
| 1   | CNPJ_COMPLETO   | VARCHAR(14) | NOT NULL | YES | CNPJ without formatting           | 12345678000199  |
| 2   | CNAE_PRINCIPAL  | VARCHAR(7)  | NOT NULL | NO  | Primary activity code (IBGE)      | 5211701         |
| 3   | CNAE_SECUNDARIO | VARCHAR     | NULL     | NO  | Secondary activities (CSV)        | 5250801,5310501 |
| 4   | UF              | VARCHAR(2)  | NOT NULL | NO  | State code (2 letters)            | SP, MG, EX      |
| 5   | NOME_MUNICIPIO  | VARCHAR     | NOT NULL | NO  | Municipality name (normalized)    | SAO PAULO       |
| 6   | CODIGO_IBGE_7   | INT         | NULL     | NO  | IBGE municipality code (7 digits) | 3550308         |
| 7   | MES_COMPETENCIA | VARCHAR(7)  | NOT NULL | NO  | Reference month (YYYY-MM)         | 2025-01         |

---

## Column Details

### 1. CNPJ_COMPLETO

- **Meaning**: Complete CNPJ (Cadastro Nacional da Pessoa Jurídica)
- **Format**: 14 numeric characters, no punctuation
- **Uniqueness**: PRIMARY KEY — one record per CNPJ (deduplicated)
- **Source**: RFB column_0 (cnpj_basico)
- **Validation**: Never NULL, always 14 digits
- **Range**: 00000000000000 — 99999999999999
- **Example**: 12345678000199 (São Paulo Logistics Corp)

### 2. CNAE_PRINCIPAL

- **Meaning**: Primary CNAE (Classificação Nacional de Atividades Econômicas)
- **Format**: 7 numeric characters (no dots)
- **Value Set**: Must be one of 11 logistics codes:
  ```
  5211701, 5211702, 5211799, 5250801, 5250802,
  5250803, 5250804, 5310501, 5320201, 5320202, 4930201
  ```
- **Source**: RFB column_11
- **Validation**: Never NULL, always in whitelist
- **Meaning** (selected examples):
  - 5211701 = Road freight transport
  - 5250801 = General warehousing (ambient temp)
  - 5310501 = Multimodal logistics operator
  - 4930201 = Urban bus transport

### 3. CNAE_SECUNDARIO

- **Meaning**: Secondary CNAE codes (comma-separated, multi-value)
- **Format**: CSV (comma-separated, no spaces)
- **Null**: May be NULL if no secondary activities declared
- **Value Set**: If present, must contain ≥1 code from 11-code whitelist
- **Source**: RFB column_12
- **Validation**: Regex pattern matching on Silver layer
- **Examples**:
  - NULL (no secondary)
  - 5250801 (single secondary)
  - 5250801,5310501 (multiple)
  - 5211701,5250802,5320201 (many)
- **Note**: Not all companies have secondary activities

### 4. UF

- **Meaning**: State/Region code (Brazilian administrative division)
- **Format**: 2 uppercase letters
- **Valid Values** (28 total):
  - **27 Brazilian states**: AC, AL, AP, AM, BA, CE, DF, ES, GO, MA, MT, MS, MG, PA, PB, PR, PE, PI, RJ, RN, RS, RO, RR, SC, SP, SE, TO
  - **1 Special code**: EX = Exterior (international entities, 184 records)
- **Source**: RFB reference (Municipios.csv) + IBGE enrichment
- **Validation**: Never NULL, must be in 28-code set
- **Distribution** (2025 annual estimate):
  - SP: 28%, MG: 16%, RJ: 14%, RS: 12%, BA: 9%, others: 21%
  - EX: 0.01% (184 records)

### 5. NOME_MUNICIPIO

- **Meaning**: Municipality name (normalized)
- **Format**: Uppercase, no accents (removed via UPPER() + normalize)
- **Examples**:
  - SAO PAULO (São Paulo)
  - BELO HORIZONTE (Belo Horizonte)
  - RIO DE JANEIRO (Rio de Janeiro)
  - EXTERIOR (special case for UF='EX')
- **Source**: RFB reference (Municipios.csv), normalized during IBGE join
- **Validation**: Never NULL after enrichment
- **Encoding**: UTF-8

### 6. CODIGO_IBGE_7

- **Meaning**: Official IBGE municipality code (7 digits)
- **Format**: 7-digit integer
- **Null**: May be NULL for:
  - UF='EX' (exterior, no IBGE code by definition)
  - Geographic join failure (~5% unmatched, logged as warning)
- **Source**: IBGE areas_ibge_2025.xls (geographic authority)
- **Validation**: If NOT NULL, must be 7-digit numeric
- **Range**: 1000001 — 9999999 (examples)
  - 3550308 = São Paulo
  - 3106200 = Belo Horizonte
  - 3304557 = Rio de Janeiro
- **Note**: NULL is expected for UF='EX'; other NULL values logged as warnings
- **Data Type**: INT (stored as integer for efficiency)

### 7. MES_COMPETENCIA

- **Meaning**: Reference month for this data batch
- **Format**: ISO 8601 YYYY-MM (not MM/YYYY)
- **Examples**: 2025-01, 2025-02, ..., 2025-12
- **Valid Range**: 2025-01 to 2025-12 (year-specific)
- **Source**: Extracted from S3 path or filename during processing
- **Validation**: Never NULL, format validated during export
- **Timezone**: All dates are business dates (no time component)
- **Interpretation**: "This record was active in January 2025"

---

## Data Quality Metrics

### Expected Distributions (2025 Annual)

**By CNAE_PRINCIPAL** (top 5):

| CNAE    | Description         | Est. Count | %   |
| ------- | ------------------- | ---------- | --- |
| 5211701 | Road freight        | 450K       | 38% |
| 5250801 | General warehousing | 280K       | 24% |
| 5211702 | Removals            | 120K       | 10% |
| 5310501 | Logistics operator  | 150K       | 12% |
| Others  | (6 more codes)      | 100K       | 8%  |

**By UF** (sample):

| UF     | Est. Count | %     |
| ------ | ---------- | ----- |
| SP     | 320K       | 28%   |
| MG     | 180K       | 16%   |
| RJ     | 160K       | 14%   |
| RS     | 140K       | 12%   |
| Others | 320K       | 28%   |
| EX     | 184        | 0.01% |

### Deduplication Impact

- **Raw records** (Bronze): 28M
- **Filtered records** (Silver, CNAE+Situacao): 2.2M (7.9% match)
- **Post-geography** (Gold enr.): 2.2M (100% enrichment success)
- **Post-deduplication** (Final): 1.8M (81.8% unique CNPJs)
- **Implication**: ~18% of Silver records were duplicates (same CNPJ, multiple updates)

---

## Known Characteristics

### Geographic Exceptions

- **UF='EX' (Exterior)**: 184 records with CODIGO_IBGE=NULL (by design, no IBGE code for exterior)
- **CODIGO_IBGE=NULL (non-EX)**: ~110K records (~6%) from join failures (RFB/IBGE name mismatches, handled via exception mapping)

### NULL Patterns

| Column          | NULL Count | Notes                                         |
| --------------- | ---------- | --------------------------------------------- |
| CNPJ_COMPLETO   | 0          | Never NULL (PK)                               |
| CNAE_PRINCIPAL  | 0          | Never NULL (always present)                   |
| CNAE_SECUNDARIO | ~40%       | OK; many companies have no secondary activity |
| UF              | 0          | Never NULL                                    |
| NOME_MUNICIPIO  | 0          | Never NULL after enrichment                   |
| CODIGO_IBGE_7   | ~6%        | OK; expected (UF='EX' + join mismatches)      |
| MES_COMPETENCIA | 0          | Never NULL                                    |

### Encoding & Normalization

- **Character set**: UTF-8 (converted from latin1 during processing)
- **Accents**: Removed from NOME_MUNICIPIO (UPPER + normalize)
- **Whitespace**: Trimmed in CNAE fields
- **Case**: UPPERCASE for most text fields (NOME_MUNICIPIO, UF)

---

## File Format Details

### Parquet (Primary Output)

- **Compression**: Snappy (efficient, fast)
- **Row Group Size**: Default (64 MB per group)
- **Metadata**: Schema, row count, statistics embedded
- **Reading**: Compatible with Pandas, Polars, PySpark, R, etc.

```python
import polars as pl
df = pl.read_parquet('receita_federal_2025.parquet')
df.shape  # (rows, cols)
```

### CSV Sample

- **Format**: Standard CSV (comma-delimited)
- **Rows**: First 100 records (for visual validation)
- **Encoding**: UTF-8
- **Headers**: Yes, 7 columns
- **Purpose**: Quick inspection, no tool needed

---

## Changelog

- **2025-05-20**: Initial data dictionary (v1.0)
  - 7 columns defined
  - Ranges and examples documented
  - Quality metrics included
