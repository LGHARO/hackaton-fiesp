"""Passo 4: trata a base inteira como um unico grupo e roda o mesmo filtro de
municipio do passo 3. Se poucos municipios ficarem perto de 100% de cobertura,
a base e de uma unica empresa.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))
from mapa_paises import build_mapa  # noqa: E402

TOL = 0.98

df = pd.read_parquet("gate_1/dados/processado/df_clusterizado.parquet")
df["mes"] = df["anomes"].str[5:7].astype(int)
df["sh4"] = df["cod_ncm"].str[:4].astype(int)
mapa_pais = build_mapa(df["pais_de_origem"])
df["co_pais"] = df["pais_de_origem"].map(mapa_pais).astype(float)
df["grupo"] = 0  # base inteira = um grupo so

perfil = (
    df.groupby(["grupo", "mes", "sh4", "co_pais"])
    .agg(vmle=("vmle_dolar", "sum"), peso=("peso_liquido", "sum"))
    .reset_index()
)
print(f"combinacoes (mes,sh4,pais) na base inteira: {len(perfil)}")

mun = pd.read_csv("shared/dados/raw/IMP_2021_MUN.csv", sep=";", encoding="latin1")
mun_perfil = (
    mun.groupby(["CO_MES", "SH4", "CO_PAIS", "CO_MUN", "SG_UF_MUN"])
    .agg(vl_fob=("VL_FOB", "sum"), kg=("KG_LIQUIDO", "sum"))
    .reset_index()
)

merged = perfil.merge(
    mun_perfil, left_on=["mes", "sh4", "co_pais"], right_on=["CO_MES", "SH4", "CO_PAIS"]
)
merged["bate"] = (merged["vl_fob"] >= TOL * merged["vmle"]) & (
    merged["kg"] >= TOL * merged["peso"]
)

total = len(perfil)
cobertura = (
    merged[merged["bate"]]
    .groupby(["CO_MUN", "SG_UF_MUN"])
    .size()
    .rename("combos_ok")
    .reset_index()
)
cobertura["cobertura"] = cobertura["combos_ok"] / total
cobertura = cobertura.sort_values("cobertura", ascending=False)
print(cobertura.head(20))
print(f"\nmax cobertura observada: {cobertura['cobertura'].max():.3f}")
