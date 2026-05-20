import os
from pathlib import Path

import polars as pl

from scripts.config import PipelineConfig
from scripts.transformer import CNPJTransformer
from scripts.utils.s3_paths import build_s3_path
from scripts.warehouse import WarehouseManager

CNAES = [
    "5211701","5211702","5211799",
    "5250801","5250802","5250803","5250804",
    "5310501","5320201","5320202","4930201",
]

def contains_cnae_sec_expr(col_name: str) -> str:
    cnaes_sql = ", ".join(f"'{c}'" for c in CNAES)
    return (
        "EXISTS ("
        f"SELECT 1 FROM UNNEST(string_split(replace(COALESCE({col_name}, ''), ' ', ''), ',')) AS x(cnae) "
        f"WHERE cnae IN ({cnaes_sql})"
        ")"
    )


def pick_temp_dir() -> str:
    # Prioriza NVMe local na EC2 quando disponivel.
    candidates = [
        "/mnt/nvme_tmp/duckdb_temp",
        "/mnt/nvme/duckdb_temp",
        "/local_nvme/duckdb_temp",
        "/scratch/tmp_duckdb",
    ]
    for c in candidates:
        p = Path(c)
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".probe"
            probe.write_text("ok", encoding="ascii")
            probe.unlink(missing_ok=True)
            return str(p)
        except Exception:
            continue

    fallback = Path.cwd() / ".tmp_duckdb"
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


def main() -> None:
    bucket = "datalake-receita-federal-massagardi"
    raw_s3 = build_s3_path("raw/receita_federal/estabelecimentos", 2025, 1)

    cfg = PipelineConfig()
    cfg.raw_path = raw_s3
    cfg.tmp_path = pick_temp_dir()
    cfg.duckdb_max_memory = "6GB"

    transformer = CNPJTransformer()
    df_silver = transformer.processar(cfg.raw_path)

    wh = WarehouseManager(cfg)
    wh.enriquecer_geografia(df_silver)

    con = wh.con
    temp_directory = con.execute("SELECT current_setting('temp_directory')").fetchone()[0]

    sec_expr = contains_cnae_sec_expr("CNAE_SECUNDARIO")
    cnaes_sql = ", ".join(f"'{c}'" for c in CNAES)

    # SELECT explícito com exatamente 7 colunas no output final.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE gold_test_2025_01 AS
        SELECT
            CAST(cnpj_basico AS VARCHAR) AS CNPJ_COMPLETO,
            CAST(cnae_principal AS VARCHAR) AS CNAE_PRINCIPAL,
            CAST(cnae_secundario AS VARCHAR) AS CNAE_SECUNDARIO,
            CAST(uf AS VARCHAR) AS UF,
            CAST(nome_municipio_rfb AS VARCHAR) AS NOME_MUNICIPIO,
            CAST(codigo_ibge_7 AS VARCHAR) AS CODIGO_IBGE,
            CONCAT('2025-', LPAD(CAST(mes_competencia AS VARCHAR), 2, '0')) AS MES_COMPETENCIA
        FROM gold_2025
        WHERE cnae_principal IN ({cnaes_sql})
           OR {sec_expr}
        """
    )

    # Tenta gravar direto no S3; fallback local NVMe + upload boto3.
    s3_output = f"s3://{bucket}/gold/test/gold_test_2025_01.parquet"
    local_output = str(Path(cfg.tmp_path) / "gold_test_2025_01.parquet")
    output_path = s3_output

    try:
        con.execute(
            """
            COPY (
                SELECT * FROM gold_test_2025_01
            ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [s3_output],
        )
    except Exception:
        con.execute(
            """
            COPY (
                SELECT * FROM gold_test_2025_01
            ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [local_output],
        )
        output_path = local_output

    # Validações obrigatórias
    cols = [r[1] for r in con.execute("PRAGMA table_info('gold_test_2025_01')").fetchall()]
    total = con.execute("SELECT COUNT(*) FROM gold_test_2025_01").fetchone()[0]
    meses_distintos = con.execute("SELECT COUNT(DISTINCT MES_COMPETENCIA) FROM gold_test_2025_01").fetchone()[0]
    mes_ok = con.execute("SELECT COUNT(*) FROM gold_test_2025_01 WHERE MES_COMPETENCIA = '2025-01'").fetchone()[0]

    sec_expr_tbl = contains_cnae_sec_expr("g.CNAE_SECUNDARIO")
    principal_expr = f"g.CNAE_PRINCIPAL IN ({cnaes_sql})"
    c_principal = con.execute(f"SELECT COUNT(*) FROM gold_test_2025_01 g WHERE {principal_expr}").fetchone()[0]
    c_sec = con.execute(f"SELECT COUNT(*) FROM gold_test_2025_01 g WHERE {sec_expr_tbl}").fetchone()[0]
    c_both = con.execute(f"SELECT COUNT(*) FROM gold_test_2025_01 g WHERE {principal_expr} AND {sec_expr_tbl}").fetchone()[0]

    nulos_mun = con.execute("SELECT COUNT(*) FROM gold_test_2025_01 WHERE NOME_MUNICIPIO IS NULL OR TRIM(NOME_MUNICIPIO) = ''").fetchone()[0]
    nulos_ibge = con.execute("SELECT COUNT(*) FROM gold_test_2025_01 WHERE CODIGO_IBGE IS NULL OR TRIM(CODIGO_IBGE) = ''").fetchone()[0]
    dups = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT CNPJ_COMPLETO, MES_COMPETENCIA, COUNT(*) c
            FROM gold_test_2025_01
            GROUP BY 1,2
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    schema_ok = cols == [
        "CNPJ_COMPLETO",
        "CNAE_PRINCIPAL",
        "CNAE_SECUNDARIO",
        "UF",
        "NOME_MUNICIPIO",
        "CODIGO_IBGE",
        "MES_COMPETENCIA",
    ]
    mes_only_ok = (meses_distintos == 1 and mes_ok == total)
    cnae_ok = (c_principal + c_sec - c_both) == total
    join_ok = (nulos_mun == 0 and nulos_ibge == 0)
    status = "APROVADO" if (schema_ok and mes_only_ok and cnae_ok and join_ok) else "REVISAR"

    print("=== TESTE GOLD 2025-01 CONCLUÍDO ===")
    print("Arquivo gerado:", output_path)
    print("Temp DuckDB:", temp_directory)
    print("Total de registros:", total)
    print("Colunas finais:", cols)
    print("Matches CNAE principal:", c_principal)
    print("Matches CNAE secundário:", c_sec)
    print("Matches ambos:", c_both)
    print("NOME_MUNICIPIO nulos:", nulos_mun)
    print("CODIGO_IBGE nulos:", nulos_ibge)
    print("Duplicidades CNPJ+MES:", dups)
    print("Schema exato (7 colunas):", schema_ok)
    print("MES_COMPETENCIA somente 2025-01:", mes_only_ok)
    print("Filtro CNAE consistente:", cnae_ok)
    print("Status:", status)


if __name__ == "__main__":
    main()
