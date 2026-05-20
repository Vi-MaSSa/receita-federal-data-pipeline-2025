"""
Extract exception mappings for geographic correction.
This script queries IBGE reference data to find correct codes for municipalities 
with name divergence between Receita Federal and IBGE.
"""
import io
import boto3
import polars as pl

# List of problematic municipalities from diagnostic
PROBLEMATIC = [
    ("8845", "RS", "SANTANA DO LIVRAMENTO"),
    ("8251", "SC", "BALNEARIO DE PICARRAS"),
    ("5875", "RJ", "PARATI"),
    ("6231", "SP", "BIRITIBA-MIRIM"),
    ("0529", "PA", "SANTA ISABEL DO PARA"),
    ("4177", "MG", "BRASOPOLIS"),
    ("9155", "MT", "SANTO ANTONIO DO LEVERGER"),
    ("0377", "PA", "ELDORADO DOS CARAJAS"),
    ("8419", "RS", "ENTRE IJUIS"),
    ("8119", "SC", "GRAO PARA"),
    ("0867", "MA", "PINDARE MIRIM"),
    ("0688", "MG", "PINGO D'AGUA"),
    ("0345", "TO", "FORTALEZA DO TABOCAO"),
    ("3005", "BA", "MUQUEM DE SAO FRANCISCO"),
    ("3869", "BA", "MALHADA DE PEDRAS"),  # UF divergence case
    ("9321", "TO", "COUTO DE MAGALHAES"),
    ("4049", "MG", "AMPARO DA SERRA"),
    ("0315", "RR", "SAO LUIZ"),
    ("1623", "RN", "ARES"),
    ("9691", "TO", "SAO VALERIO DA NATIVIDADE"),
    ("1703", "RN", "BOA SAUDE"),
    ("3101", "SE", "AMPARO DE SAO FRANCISCO"),
    ("9707", "EX", "EXTERIOR"),  # Special exterior case
]

# Load IBGE reference
print("Loading IBGE reference from S3...")
s3 = boto3.client("s3")
obj = s3.get_object(
    Bucket="datalake-receita-federal-massagardi",
    Key="reference/ibge/areas_ibge_2025.xls"
)
df_ibge = pl.read_excel(io.BytesIO(obj["Body"].read()), engine="calamine")

# Normalize IBGE names for matching
df_ibge = df_ibge.with_columns([
    pl.col("NM_UF_SIGLA").cast(pl.Utf8).str.to_uppercase(),
    pl.col("NM_MUN").cast(pl.Utf8).str.to_uppercase().str.replace_all(" ", ""),
    pl.col("CD_MUN").cast(pl.Utf8),
])

print("\nSearching for IBGE codes...")
for cod_rfb, uf_rfb, nome_rfb in PROBLEMATIC:
    normalized_nome = nome_rfb.replace(" ", "").upper()
    
    # First try exact UF match
    match = df_ibge.filter(
        (pl.col("NM_UF_SIGLA") == uf_rfb) &
        (pl.col("NM_MUN") == normalized_nome)
    )
    
    if match.height > 0:
        row = match.row(0)
        ibge_code = row[df_ibge.columns.index("CD_MUN")]
        ibge_name = row[df_ibge.columns.index("NM_MUN")]
        print(f"✓ Found ({cod_rfb}, {uf_rfb}): IBGE={ibge_code} ({ibge_name})")
    else:
        # Try fuzzy match by name only (for UF divergence cases)
        match_name = df_ibge.filter(
            pl.col("NM_MUN").str.contains(normalized_nome[:8])
        )
        
        if match_name.height > 0:
            print(f"⚠ Fuzzy matches for {cod_rfb} ({uf_rfb}): {nome_rfb}")
            for r in match_name.iter_rows(named=True):
                print(f"    → {r['NM_UF_SIGLA']}: {r['NM_MUN']} (CD={r['CD_MUN']})")
        else:
            print(f"✗ No match found for ({cod_rfb}, {uf_rfb}): {nome_rfb}")
