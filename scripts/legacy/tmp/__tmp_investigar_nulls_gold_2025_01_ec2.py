from __future__ import annotations

import duckdb
import polars as pl

from scripts.config import PipelineConfig
from scripts.transformer import CNPJTransformer
from scripts.utils.s3_paths import build_s3_path
from scripts.warehouse import WarehouseManager

CNAES = [
    "5211701", "5211702", "5211799",
    "5250801", "5250802", "5250803", "5250804",
    "5310501", "5320201", "5320202", "4930201",
]


def contains_cnae_sec_expr(col_name: str) -> str:
    cnaes_sql = ", ".join(f"'{c}'" for c in CNAES)
    return (
        "EXISTS ("
        f"SELECT 1 FROM UNNEST(string_split(replace(COALESCE({col_name}, ''), ' ', ''), ',')) AS x(cnae) "
        f"WHERE cnae IN ({cnaes_sql})"
        ")"
    )


def main() -> None:
    cfg = PipelineConfig()
    cfg.raw_path = build_s3_path("raw/receita_federal/estabelecimentos", 2025, 1)
    cfg.tmp_path = "/mnt/nvme_tmp/duckdb_temp"
    cfg.duckdb_max_memory = "6GB"

    print("[env] raw_path=", cfg.raw_path, flush=True)
    print("[env] tmp_path=", cfg.tmp_path, flush=True)

    transformer = CNPJTransformer()
    df_silver = transformer.processar(cfg.raw_path)
    print("[silver] rows=", df_silver.height, flush=True)

    wh = WarehouseManager(cfg)
    wh.enriquecer_geografia(df_silver)
    con = wh.con

    cnaes_sql = ", ".join(f"'{c}'" for c in CNAES)
    sec_expr = contains_cnae_sec_expr("g.cnae_secundario")

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE gold_test_diag AS
        SELECT
            CAST(g.cnpj_basico AS VARCHAR) AS cnpj_completo,
            CAST(g.cnae_principal AS VARCHAR) AS cnae_principal,
            CAST(g.cnae_secundario AS VARCHAR) AS cnae_secundario,
            CAST(g.uf AS VARCHAR) AS uf,
            CAST(g.cod_mun_rfb AS VARCHAR) AS cod_mun_rfb,
            CAST(g.nome_municipio_rfb AS VARCHAR) AS nome_municipio,
            CAST(g.codigo_ibge_7 AS VARCHAR) AS codigo_ibge,
            CONCAT('2025-', LPAD(CAST(g.mes_competencia AS VARCHAR), 2, '0')) AS mes_competencia
        FROM gold_2025 g
        WHERE g.cnae_principal IN ({cnaes_sql})
           OR {sec_expr}
        """
    )

    total = con.execute("SELECT COUNT(*) FROM gold_test_diag").fetchone()[0]
    nulos_nome = con.execute(
        "SELECT COUNT(*) FROM gold_test_diag WHERE nome_municipio IS NULL OR TRIM(nome_municipio) = ''"
    ).fetchone()[0]
    nulos_ibge = con.execute(
        "SELECT COUNT(*) FROM gold_test_diag WHERE codigo_ibge IS NULL OR TRIM(codigo_ibge) = ''"
    ).fetchone()[0]
    ambos_nulos = con.execute(
        """
        SELECT COUNT(*)
        FROM gold_test_diag
        WHERE (nome_municipio IS NULL OR TRIM(nome_municipio) = '')
          AND (codigo_ibge IS NULL OR TRIM(codigo_ibge) = '')
        """
    ).fetchone()[0]
    so_nome = con.execute(
        """
        SELECT COUNT(*)
        FROM gold_test_diag
        WHERE (nome_municipio IS NULL OR TRIM(nome_municipio) = '')
          AND NOT (codigo_ibge IS NULL OR TRIM(codigo_ibge) = '')
        """
    ).fetchone()[0]
    so_ibge = con.execute(
        """
        SELECT COUNT(*)
        FROM gold_test_diag
        WHERE NOT (nome_municipio IS NULL OR TRIM(nome_municipio) = '')
          AND (codigo_ibge IS NULL OR TRIM(codigo_ibge) = '')
        """
    ).fetchone()[0]

    print("\n=== RESUMO NULOS ===", flush=True)
    print("total_registros=", total, flush=True)
    print("nulos_nome_municipio=", nulos_nome, flush=True)
    print("nulos_codigo_ibge=", nulos_ibge, flush=True)
    print("ambos_nulos=", ambos_nulos, flush=True)
    print("so_nome_nulo=", so_nome, flush=True)
    print("so_ibge_nulo=", so_ibge, flush=True)

    print("\n=== NULOS POR UF ===", flush=True)
    uf_rows = con.execute(
        """
        SELECT uf, COUNT(*) AS qtd
        FROM gold_test_diag
        WHERE (nome_municipio IS NULL OR TRIM(nome_municipio) = '')
           OR (codigo_ibge IS NULL OR TRIM(codigo_ibge) = '')
        GROUP BY uf
        ORDER BY qtd DESC, uf
        """
    ).fetchall()
    for row in uf_rows:
        print(row, flush=True)

    print("\n=== AMOSTRA 100 REGISTROS NULOS ===", flush=True)
    sample_rows = con.execute(
        """
        SELECT cnpj_completo, uf, cnae_principal, cnae_secundario, cod_mun_rfb, nome_municipio, codigo_ibge, mes_competencia
        FROM gold_test_diag
        WHERE nome_municipio IS NULL OR TRIM(nome_municipio) = ''
        ORDER BY uf, cod_mun_rfb, cnpj_completo
        LIMIT 100
        """
    ).fetchall()
    for row in sample_rows:
        print(row, flush=True)

    print("\n=== REFERENCE MUNICIPIOS: DIAGNÓSTICO DE CÓDIGO ===", flush=True)
    ref_stats = con.execute(
        """
        SELECT
            COUNT(*) AS total_ref,
            COUNT(*) FILTER (WHERE COD_MUN_RFB IS NULL OR TRIM(CAST(COD_MUN_RFB AS VARCHAR)) = '') AS cod_null_blank,
            COUNT(*) FILTER (WHERE LENGTH(TRIM(CAST(COD_MUN_RFB AS VARCHAR))) < 4) AS cod_len_lt4,
            MIN(LENGTH(TRIM(CAST(COD_MUN_RFB AS VARCHAR)))) AS min_len,
            MAX(LENGTH(TRIM(CAST(COD_MUN_RFB AS VARCHAR)))) AS max_len
        FROM municipios_rfb
        """
    ).fetchone()
    print(ref_stats, flush=True)

    print("\n=== CAUSAS PROVÁVEIS DOS NULOS ===", flush=True)
    cause_rows = con.execute(
        """
        WITH nulls AS (
            SELECT *
            FROM gold_test_diag
            WHERE (nome_municipio IS NULL OR TRIM(nome_municipio) = '')
               OR (codigo_ibge IS NULL OR TRIM(codigo_ibge) = '')
        )
        SELECT
            CASE
                WHEN n.uf = 'EX' THEN 'uf_especial_exterior'
                WHEN m.COD_MUN_RFB IS NULL THEN 'codigo_v21_inexistente_em_municipios'
                WHEN gm.codigo_ibge_7 IS NULL THEN 'municipio_sem_match_no_ibge_por_nome'
                WHEN gm.uf_ibge IS NOT NULL AND UPPER(TRIM(n.uf)) <> UPPER(TRIM(gm.uf_ibge)) THEN 'divergencia_uf_vs_ibge'
                ELSE 'outra_causa'
            END AS causa,
            COUNT(*) AS qtd
        FROM nulls n
        LEFT JOIN municipios_rfb m
          ON LPAD(TRIM(CAST(n.cod_mun_rfb AS VARCHAR)), 4, '0') = LPAD(TRIM(CAST(m.COD_MUN_RFB AS VARCHAR)), 4, '0')
        LEFT JOIN geografia_master gm
          ON LPAD(TRIM(CAST(n.cod_mun_rfb AS VARCHAR)), 4, '0') = LPAD(TRIM(CAST(gm.cod_mun_rfb AS VARCHAR)), 4, '0')
        GROUP BY 1
        ORDER BY qtd DESC, causa
        """
    ).fetchall()
    for row in cause_rows:
        print(row, flush=True)

    print("\n=== CÓDIGOS V21 SEM MATCH (TOP 100) ===", flush=True)
    unmatched_codes = con.execute(
        """
        WITH nulls AS (
            SELECT *
            FROM gold_test_diag
            WHERE (nome_municipio IS NULL OR TRIM(nome_municipio) = '')
               OR (codigo_ibge IS NULL OR TRIM(codigo_ibge) = '')
        )
        SELECT
            LPAD(TRIM(CAST(n.cod_mun_rfb AS VARCHAR)), 4, '0') AS codigo_v21,
            n.uf,
            COUNT(*) AS total_ocorrencias,
            CASE
                WHEN n.uf = 'EX' THEN 'uf_especial_exterior'
                WHEN m.COD_MUN_RFB IS NULL THEN 'inexistente_em_municipios'
                WHEN gm.codigo_ibge_7 IS NULL THEN 'sem_match_ibge'
                WHEN gm.uf_ibge IS NOT NULL AND UPPER(TRIM(n.uf)) <> UPPER(TRIM(gm.uf_ibge)) THEN 'divergencia_uf'
                ELSE 'outra'
            END AS causa
        FROM nulls n
        LEFT JOIN municipios_rfb m
          ON LPAD(TRIM(CAST(n.cod_mun_rfb AS VARCHAR)), 4, '0') = LPAD(TRIM(CAST(m.COD_MUN_RFB AS VARCHAR)), 4, '0')
        LEFT JOIN geografia_master gm
          ON LPAD(TRIM(CAST(n.cod_mun_rfb AS VARCHAR)), 4, '0') = LPAD(TRIM(CAST(gm.cod_mun_rfb AS VARCHAR)), 4, '0')
        GROUP BY 1,2,4
        ORDER BY total_ocorrencias DESC, codigo_v21, uf
        LIMIT 100
        """
    ).fetchall()
    for row in unmatched_codes:
        print(row, flush=True)

    print("\n=== MUNICÍPIOS RFB ENCONTRADOS MAS SEM IBGE (TOP 100) ===", flush=True)
    ibge_fail_rows = con.execute(
        """
        WITH nulls AS (
            SELECT *
            FROM gold_test_diag
            WHERE (nome_municipio IS NULL OR TRIM(nome_municipio) = '')
               OR (codigo_ibge IS NULL OR TRIM(codigo_ibge) = '')
        )
        SELECT
            LPAD(TRIM(CAST(n.cod_mun_rfb AS VARCHAR)), 4, '0') AS codigo_v21,
            m.NOME_MUN_RFB,
            COUNT(*) AS total_ocorrencias
        FROM nulls n
        JOIN municipios_rfb m
          ON LPAD(TRIM(CAST(n.cod_mun_rfb AS VARCHAR)), 4, '0') = LPAD(TRIM(CAST(m.COD_MUN_RFB AS VARCHAR)), 4, '0')
        LEFT JOIN geografia_master gm
          ON LPAD(TRIM(CAST(n.cod_mun_rfb AS VARCHAR)), 4, '0') = LPAD(TRIM(CAST(gm.cod_mun_rfb AS VARCHAR)), 4, '0')
        WHERE gm.codigo_ibge_7 IS NULL
        GROUP BY 1,2
        ORDER BY total_ocorrencias DESC, codigo_v21
        LIMIT 100
        """
    ).fetchall()
    for row in ibge_fail_rows:
        print(row, flush=True)

    impact_pct = (ambos_nulos / total * 100.0) if total else 0.0
    print("\n=== IMPACTO ===", flush=True)
    print(f"impacto_percentual={impact_pct:.4f}%", flush=True)


if __name__ == "__main__":
    main()
