# Execution Guide — Receita Federal 2025 Pipeline

## Quick Start (5 minutes)

```bash
# 1. Clone & navigate
git clone <repo-url>
cd pipeline_dados_receita_federal

# 2. Create virtual environment
python -m venv venv_dados
source venv_dados/bin/activate        # Linux/Mac
# OR
.\venv_dados\Scripts\activate         # Windows PowerShell

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env if needed (usually not for local dry run)

# 5. Run pipeline (1 month dry run)
python -m scripts.main --raw-path dados_brutos/2025-01

# ✓ Success! Check output/ for results
```

---

## Installation

### System Requirements

- **Python**: 3.10+
- **RAM**: 2 GB minimum (local dry run), 8+ GB recommended (production)
- **Disk**: 50 GB free (for temp DuckDB spill-to-disk)
- **OS**: Linux, macOS, or Windows (with PowerShell or WSL)

### Step 1: Python Virtual Environment

```bash
# Create venv
python -m venv venv_dados

# Activate
source venv_dados/bin/activate        # Linux/Mac
# OR
.\venv_dados\Scripts\activate         # Windows
# OR (WSL)
source venv_dados/Scripts/activate

# Verify
which python                          # Should show path inside venv_dados/
python --version                      # Should be 3.10+
```

### Step 2: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Core packages**:

- Polars (0.x) — streaming CSV read
- DuckDB — OLAP processing
- Boto3 — S3 integration
- Python-Calamine — Excel read
- PyArrow — Parquet serialization

### Step 3: Configuration

```bash
# Copy template
cp .env.example .env

# Edit .env (usually no changes needed for local)
# vim .env
```

See `.env.example` for all options.

---

## Local Execution

### Mode 1: Dry Run (1 Month)

**Purpose**: Test pipeline, validate data flow, quick iteration

```bash
python -m scripts.main --raw-path dados_brutos/2025-01

# Expected output:
# ✓ logs/pipeline_YYYYMMDD_HHMMSS.log  (~100 KB)
# ✓ output/receita_federal_2025_jan.parquet  (~125 MB)
# ✓ output/resumo_2025_jan.xlsx  (~2.5 MB, with charts)
# ✓ output/amostra_100linhas.csv  (~50 KB, sample)

# Time: ~9 minutes
# Memory: ~2 GB peak
```

### Mode 2: Full Year

**Purpose**: Pre-production validation, full dataset processing

```bash
python -m scripts.main --raw-path dados_brutos/2025

# Expected output:
# ✓ output/receita_federal_2025.parquet  (~1.5 GB)
# ✓ output/resumo_2025.xlsx  (~50 MB)
# ✓ output/amostra_100linhas.csv  (~50 KB)

# Time: ~90 minutes
# Memory: ~2 GB peak (streaming, constant)
# Temp: ~50 GB (DuckDB spill-to-disk in .tmp_duckdb/)
```

---

## AWS Production

### Prerequisites

1. **EC2 Instance**:
   - Type: r7g.xlarge (32 GB RAM, Graviton3) or larger
   - OS: Ubuntu 22.04 LTS or Amazon Linux 2
   - IAM Role: S3 read/write permissions

2. **S3 Bucket**:
   - Raw data uploaded: `s3://bucket/raw/receita_federal/estabelecimentos/ano=2025/mes=*/`
   - Reference data: `s3://bucket/reference/municipios/`, `reference/ibge/`

3. **IAM Role** (recommended over keys):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:ListBucket", "s3:PutObject"],
         "Resource": ["arn:aws:s3:::your-bucket/*", "arn:aws:s3:::your-bucket"]
       }
     ]
   }
   ```

### Setup on EC2

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install Python 3.10
sudo apt install -y python3.10 python3.10-venv python3.10-dev git

# 3. Clone repo
git clone <repo-url>
cd pipeline_dados_receita_federal

# 4. Create venv (using python3.10)
python3.10 -m venv venv_dados
source venv_dados/bin/activate

# 5. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 6. Configure .env
cp .env.example .env
# Edit .env
# ENV=aws
# S3_BUCKET=your-bucket-name
```

### Execution on AWS

```bash
# Set environment variables (or use .env)
export ENV=aws
export S3_BUCKET=your-bucket-name
export AWS_REGION=sa-east-1
# MOTHERDUCK_TOKEN=your_token  (optional, for MotherDuck analytics)

# Run pipeline (automatically reads from S3, outputs to S3)
python -m scripts.main

# Logs to console + logs/pipeline_*.log
# Outputs to s3://your-bucket-name/gold/receita_federal/.../ano=2025/mes=*/
```

---

## MotherDuck (Optional Cloud Analytics)

**What**: Hybrid local/cloud DuckDB with shared dashboard & SQL interface

### Setup

1. **Get token**:
   - Sign up at motherduck.com
   - Generate API token from settings

2. **Configure**:

   ```bash
   export MOTHERDUCK_TOKEN=your_token_here
   # OR add to .env
   # MOTHERDUCK_TOKEN=your_token_here
   ```

3. **Run**:

   ```bash
   python -m scripts.main --raw-path dados_brutos/2025-01 --token your_token_here
   # OR if MOTHERDUCK_TOKEN in .env
   python -m scripts.main --raw-path dados_brutos/2025-01
   ```

4. **Query**:
   ```bash
   # Connect via MotherDuck Web Console
   # SELECT * FROM receita_2025.gold_2025 WHERE uf='SP'
   # Create dashboards, share results
   ```

---

## Post-Execution Validation

### Check Parquet

```bash
python -c "
import polars as pl
df = pl.read_parquet('output/receita_federal_2025.parquet')
print(f'Rows: {len(df)}')
print(f'Columns: {df.columns}')
print(f'Schema: {df.schema}')
print(df.head())
"
```

### Check CSV Sample

```bash
head -20 output/amostra_100linhas.csv
# Should show 100 lines with proper headers and data
```

### View Excel Summary

```bash
# Open in Excel, LibreOffice, or Google Sheets
output/resumo_2025.xlsx
# Check sheets: Data, By CNAE, By UF, Summary
```

### Check Logs

```bash
tail -50 logs/pipeline_*.log
# Look for:
# ✓ [INICIO] Pipeline
# ✓ [CNPJTransformer] Silver: X registros
# ✓ [WarehouseManager] Gold: X registros
# ✓ [FIM] Pipeline concluído com sucesso
```

---

## Troubleshooting

### Error: "No module named 'scripts'"

```bash
# ❌ Wrong
python scripts/main.py

# ✅ Correct
python -m scripts.main
```

### Error: "MOTHERDUCK_TOKEN not found" (but MotherDuck optional)

```bash
# Just use local DuckDB :memory:
unset MOTHERDUCK_TOKEN
python -m scripts.main
```

### Error: "S3_BUCKET not defined" (AWS mode)

```bash
export S3_BUCKET=your-bucket-name
export ENV=aws
python -m scripts.main
```

### Slow on Small Machine?

```bash
# Use NVMe SSD for temp directory
export DUCKDB_TEMP_DIR=/mnt/nvme/duckdb_temp
# Or process 1 month at a time
python -m scripts.main --raw-path dados_brutos/2025-01
```

### BadZipFile Errors (Already Handled)

```bash
# Pipeline logs warning and continues
# Check logs/ for which ZIP was skipped
grep BadZipFile logs/pipeline_*.log
```

---

## CLI Reference

```bash
python -m scripts.main --help

# Options:
#   --raw-path PATH
#     Override input data path
#     Examples:
#       ../dados_brutos/2025-01         (local, dry run)
#       ../dados_brutos/2025            (local, full year)
#       s3://bucket/raw/.../ano=2025/   (AWS S3)
#
#   --token TOKEN
#     MotherDuck token (overrides env var)
#     Example:
#       --token your_token_here
```

---

## Example: Full Workflow

```bash
# 1. Setup
git clone <repo>
cd pipeline_dados_receita_federal
python -m venv venv_dados
source venv_dados/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 2. Dry run (validate)
python -m scripts.main --raw-path dados_brutos/2025-01
# Monitor: tail -f logs/pipeline_*.log

# 3. Verify output
python -c "
import polars as pl
df = pl.read_parquet('output/receita_federal_2025_jan.parquet')
print(f'✓ {len(df)} records in Gold')
"

# 4. Open Excel summary
# (Check distributions by CNAE and UF)

# 5. Full year (production)
python -m scripts.main --raw-path dados_brutos/2025

# 6. Export to S3 (if AWS)
export ENV=aws
export S3_BUCKET=your-bucket
python -m scripts.main

# ✓ Complete!
```
