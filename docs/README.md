## 📊 Data Source

This project uses publicly available data from the Brazilian Federal Revenue Service (Receita Federal).

- **Source:** https://dados.gov.br / Receita Federal

- **License:** CC BY-ND 3.0

- **Usage:** Data is used for educational and analytical purposes only

---

## 🚀 Improvements in this version

- ❌ Removed automatic download

- ✅ Local ZIP file processing

- ✅ Raw / staging / curated layer separation

- ✅ Parallel processing → partitioned Parquet

- ✅ Final merge using DuckDB

- ✅ Data enrichment with DuckDB (disk-based, no RAM overload)

- ✅ Fully scalable pipeline

---

## 🐍 Python Environment Setup

This project uses a virtual environment to isolate dependencies.

### 1. Create virtual environment

```bash

python  -m  venv  venv_dados

### 2. Activate environment
**Windows:**

venv_dados\Scripts\activate

**Linux/Mac:**

source venv_dados/bin/activate

### 3. Install dependencies
pip install -r requirements.txt]

## ⚠️ Notes

> The virtual environment folder (`venv_dados/`) is not included in the repository.
> Make sure to create it locally before running the project.
```
