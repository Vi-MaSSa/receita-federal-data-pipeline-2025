# Business Rules — Receita Federal 2025 Logistics

## CNAE Filters (Immutable)

### 11 Target CNAEs (Logística Roteiro Vinícius)

```
GROUP 52.11: Transportes rodoviários
  • 5211701: Transporte de carga rodoviário
  • 5211702: Transporte de mudanças
  • 5211799: Outros transportes rodoviários

GROUP 52.50: Depósitos e armazéns
  • 5250801: Armazenagem e depósitos — temperatura ambiente
  • 5250802: Armazenagem e depósitos — frigoríficos
  • 5250803: Silos
  • 5250804: Estruturas de armazenagem móveis

GROUP 53.10: Operadores de transporte logístico
  • 5310501: Operador de transporte multimodal

GROUP 53.20: Transportes especializados
  • 5320201: Transporte de valores
  • 5320202: Transporte de combustível

GROUP 49.30: Transporte urbano
  • 4930201: Transporte rodoviário urbano em ônibus
```

**Application**:

- Filter on `CNAE_PRINCIPAL` OR `CNAE_SECUNDARIO` (multi-value field)
- **Regex**: `(?:^|,)(5211701|5211702|...)(?:,|$)`
- **Matching**: Case-insensitive, comma-separated support
- **Impact**: ~7.9% match rate (2.2M from 28M total RFB records)

---

## CNAE_PRINCIPAL (Always Required)

- **Type**: VARCHAR(7)
- **Requirement**: NEVER NULL, ALWAYS in 11-code list
- **Source**: RFB column_11
- **Validation**: Enforced in Silver layer filter

---

## CNAE_SECUNDARIO (May Contain Logistics CNAEs)

- **Type**: VARCHAR (comma-separated list)
- **Requirement**: May be NULL; if present, must contain ≥1 CNAE from list
- **Source**: RFB column_12
- **Validation**: Regex pattern matching
- **Examples**:
  - NULL (no secondary CNAEs)
  - "5250801" (single)
  - "5250801,5310501,5320201" (multiple)

---

## Situação Cadastral (Active Only)

- **Filter**: `situacao_cadastral == "02"` (ATIVA)
- **Definition**: Only active establishments included in output
- **Exclusions**: All other codes (01=Nula, 03=Suspensa, 04=Inapta, 05=Cancelada, etc.)
- **Impact**: ~30% of records filtered out
- **Enforcement**: Silver layer, pre-Gold

---

## Geographic Enrichment

### Join with Municipios.csv (RFB Reference)

- **Key**: `cod_mun_rfb` (6-digit municipal code)
- **Source**: RFB reference data (included in S3)
- **Output**: `nome_municipio`, `uf`
- **Type**: LEFT JOIN (keeps records even if not found)
- **Frequency**: Rare not found (< 0.1%)

### Join with IBGE (areas_ibge_2025.xls)

- **Keys**: `nome_municipio` + `uf` (normalized, accents removed)
- **Source**: IBGE reference data (Brazilian geographic authority)
- **Output**: `codigo_ibge_7` (7-digit IBGE code for municipality)
- **Type**: LEFT JOIN (NULL if not matched)
- **Frequency**: ~5% unmatched (handled via exceptions mapping)

### Geographic Exceptions (UF='EX')

**Exterior establishments (184 records in 2025)**:

- **UF**: 'EX' (exterior code)
- **Problem**: No municipality exists in IBGE for "exterior"
- **Solution**: Map to `CODIGO_IBGE = NULL` by design (per business rules)
- **Source**: `scripts/warehouse/geographic_exceptions.py` (EXCEPTION_MAP)
- **Audit**: Explicitly logged and counted

**Other exceptions**:

- RFB/IBGE name divergences (accents, abbreviations, spelling)
- **Example**: "São Paulo" (RFB) vs "Sao Paulo" (IBGE) → manual mapping
- **Maintenance**: Exception map in geographic_exceptions.py with audit trail

---

## Deduplication

- **Logic**: GROUP BY `CNPJ_COMPLETO`
- **Strategy**: Keep 1st record per CNPJ (or MAX by date if tracked)
- **Impact**: ~17.9% of records removed (multiple records per CNPJ across RFB updates)
- **Output**: 1 unique CNPJ per row guaranteed
- **Audit**: Dedup count logged (before/after comparison)

---

## GOLD Schema (Immutable Contract)

```sql
CREATE TABLE gold_2025 (
  cnpj_completo       VARCHAR(14) PRIMARY KEY,    -- NOT NULL, unique
  cnae_principal      VARCHAR(7) NOT NULL,        -- Always in list of 11
  cnae_secundario     VARCHAR,                    -- NULL or CSV of CNAEs
  uf                  VARCHAR(2) NOT NULL,        -- 27 UFs + 'EX'
  nome_municipio      VARCHAR NOT NULL,           -- Normalized, uppercase
  codigo_ibge_7       INT,                        -- NULL for UF='EX' or join fail
  mes_competencia     VARCHAR(7) NOT NULL         -- YYYY-MM format
);
```

**Constraints**:

- ❌ No columns may be added/removed without business approval
- ❌ No field types may change
- ❌ No NULL policy may be relaxed
- ✅ New indexes (performance) allowed without approval
- ✅ New partition schemes allowed without approval

---

## Validation Rules

| Validation                       | Stage           | Action                  |
| -------------------------------- | --------------- | ----------------------- |
| Schema columns (30 min)          | Bronze → Silver | Log warning, skip file  |
| Encoding (latin1/utf-8)          | Silver          | Fallback latin1 → utf-8 |
| CNPJ not NULL                    | Silver          | Remove row              |
| CNAE not in list                 | Silver          | Remove row              |
| Situacao != '02'                 | Silver          | Remove row              |
| Duplicate CNPJ                   | Gold            | Dedup (keep 1st)        |
| Missing CODIGO_IBGE (UF != 'EX') | Gold            | Log warning (join fail) |
| Schema mismatch (7 cols, types)  | Export          | Fail loudly             |

---

## Data Quality Metrics

### Expected Outcomes (2025 Annual)

| Metric                       | Value | %                       |
| ---------------------------- | ----- | ----------------------- |
| Raw records (Bronze)         | 28.0M | 100%                    |
| CNAE match (Silver)          | 2.2M  | 7.9%                    |
| Post-geography (Gold)        | 2.2M  | 100% (input)            |
| Post-dedup (Final)           | 1.8M  | 81.8% (unique CNPJs)    |
| UF='EX' (special case)       | 184   | 0.01%                   |
| NULL CODIGO_IBGE (join fail) | ~110K | 6.1% (expected, mapped) |

### Quality Assurance Checklist

- ✓ All CNPJ_COMPLETO are 14 digits
- ✓ All CNAE_PRINCIPAL in list of 11
- ✓ All UF are valid (27 + EX)
- ✓ No NULL CNPJ_COMPLETO
- ✓ No NULL UF
- ✓ No NULL MES_COMPETENCIA
- ✓ MES_COMPETENCIA format is YYYY-MM
- ✓ No duplicate CNPJ
- ✓ Parquet schema matches SQL definition
