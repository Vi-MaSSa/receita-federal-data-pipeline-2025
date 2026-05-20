import io
from pathlib import Path

import boto3
import duckdb
import polars as pl

parquet_path = "/mnt/nvme_tmp/duckdb_temp/gold_test_2025_01.parquet"
print("parquet_path=", parquet_path)
print("exists=", Path(parquet_path).exists())

con = duckdb.connect(":memory:")
safe_parquet = parquet_path.replace("'", "''")
con.execute(f"CREATE VIEW gold AS SELECT * FROM read_parquet('{safe_parquet}')")

total = con.execute("SELECT COUNT(*) FROM gold").fetchone()[0]
nulls = con.execute(
    """
    SELECT COUNT(*)
    FROM gold
    WHERE NOME_MUNICIPIO IS NULL OR TRIM(CAST(NOME_MUNICIPIO AS VARCHAR)) = ''
       OR CODIGO_IBGE IS NULL OR TRIM(CAST(CODIGO_IBGE AS VARCHAR)) = ''
    """
).fetchone()[0]
print("total_registros=", total)
print("registros_com_nulo_mun_ou_ibge=", nulls)

print("\n[1] Nulos por UF")
uf_rows = con.execute(
    """
    SELECT UF,
           COUNT(*) AS total_uf,
           COUNT(*) FILTER (WHERE NOME_MUNICIPIO IS NULL OR TRIM(CAST(NOME_MUNICIPIO AS VARCHAR)) = '') AS nulos_nome_municipio,
           COUNT(*) FILTER (WHERE CODIGO_IBGE IS NULL OR TRIM(CAST(CODIGO_IBGE AS VARCHAR)) = '') AS nulos_codigo_ibge
    FROM gold
    GROUP BY UF
    HAVING nulos_nome_municipio > 0 OR nulos_codigo_ibge > 0
    ORDER BY (nulos_nome_municipio + nulos_codigo_ibge) DESC, UF
    """
).fetchall()
for r in uf_rows:
    print(r)

print("\n[2] Amostra de registros com NOME_MUNICIPIO nulo")
sample = con.execute(
    """
    SELECT CNPJ_COMPLETO, CNAE_PRINCIPAL, CNAE_SECUNDARIO, UF, NOME_MUNICIPIO, CODIGO_IBGE, MES_COMPETENCIA
    FROM gold
    WHERE NOME_MUNICIPIO IS NULL OR TRIM(CAST(NOME_MUNICIPIO AS VARCHAR)) = ''
    LIMIT 25
    """
).fetchall()
for r in sample:
    print(r)

candidates = [
    "/mnt/nvme_tmp/duckdb_temp/base_receita_federal_2025.parquet",
    "/mnt/nvme_tmp/duckdb_temp/gold_2025.parquet",
    "/mnt/nvme_tmp/duckdb_temp/gold_2025_final.parquet",
    "/home/ec2-user/pipeline_dados_receita_federal/pipeline_dados_receita_federal_upload/output/base_receita_federal_2025.parquet",
]
existing = [p for p in candidates if Path(p).exists()]
print("\n[3] Upstream parquet candidates:", existing)

if existing:
    src = existing[0]
    safe_src = src.replace("'", "''")
    con.execute(f"CREATE VIEW src_gold AS SELECT * FROM read_parquet('{safe_src}')")
    cols = [c[0] for c in con.execute("DESCRIBE SELECT * FROM src_gold").fetchall()]
    print("[3] upstream columns:", cols)

    if "cod_mun_rfb" in cols:
        s3 = boto3.client("s3")
        obj = s3.get_object(
            Bucket="datalake-receita-federal-massagardi",
            Key="reference/municipios/Municipios.csv",
        )
        ref_df = pl.read_csv(
            io.BytesIO(obj["Body"].read()),
            separator=";",
            has_header=False,
            new_columns=["COD_MUN_RFB", "NOME_MUN_RFB"],
            encoding="iso-8859-1",
        ).with_columns(
            [
                pl.col("COD_MUN_RFB").cast(pl.Utf8, strict=False).str.strip_chars().str.zfill(4),
                pl.col("NOME_MUN_RFB").cast(pl.Utf8, strict=False).str.strip_chars().str.to_uppercase(),
            ]
        )
        con.register("ref_mun", ref_df)

        where_mes = ""
        if "mes_competencia" in cols:
            where_mes = "WHERE CAST(mes_competencia AS VARCHAR) IN ('01','1','2025-01')"

        unmatched_sql = f"""
            SELECT
                LPAD(TRIM(CAST(s.cod_mun_rfb AS VARCHAR)), 4, '0') AS cod_mun_rfb,
                COALESCE(TRIM(CAST(s.uf AS VARCHAR)), '') AS uf,
                COUNT(*) AS qtd
            FROM src_gold s
            LEFT JOIN ref_mun r
              ON LPAD(TRIM(CAST(s.cod_mun_rfb AS VARCHAR)), 4, '0') = r.COD_MUN_RFB
            {where_mes}
              AND (r.COD_MUN_RFB IS NULL)
            GROUP BY 1,2
            ORDER BY qtd DESC, cod_mun_rfb
            LIMIT 50
        """
        unmatched = con.execute(unmatched_sql).fetchall()

        print("\n[4] Códigos município RFB sem match em reference/municipios (top 50)")
        for r in unmatched:
            print(r)

        pad_sql = f"""
            SELECT
              COUNT(*) AS total_rows,
              COUNT(*) FILTER (WHERE LENGTH(TRIM(CAST(cod_mun_rfb AS VARCHAR))) < 4) AS cod_len_lt4,
              COUNT(*) FILTER (WHERE TRIM(CAST(cod_mun_rfb AS VARCHAR)) = '') AS cod_blank
            FROM src_gold
            {where_mes}
        """
        pad_stats = con.execute(pad_sql).fetchone()
        print("\n[5] Diagnóstico de padding/código V21 no upstream:", pad_stats)
    else:
        print("[4] Não foi possível listar códigos sem match: coluna cod_mun_rfb ausente no upstream encontrado.")
else:
    print("[4] Não há parquet upstream com cod_mun_rfb disponível no host para mapear códigos sem match sem reprocessar.")

print("\n[6] Conclusão preliminar automática:")
if nulls == 0:
    print("Sem nulos em municipio/ibge neste arquivo.")
else:
    print("Há nulos e as contagens por UF foram listadas acima; usar resultado [4]/[5] para distinguir código ausente/padding/referência.")
