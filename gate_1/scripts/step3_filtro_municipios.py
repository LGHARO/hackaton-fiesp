"""Passo 3: candidatos de municipio por grupo, cruzando com Comex Stat IMP_2021_MUN,
usando mes + SH4 + CO_PAIS + faixa de valor/peso.
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

grupo_perfil = (
    df.groupby(["grupo", "mes", "sh4", "co_pais"])
    .agg(vmle=("vmle_dolar", "sum"), peso=("peso_liquido", "sum"))
    .reset_index()
)

mun = pd.read_csv("shared/dados/raw/IMP_2021_MUN.csv", sep=";", encoding="latin1")
mun_perfil = (
    mun.groupby(["CO_MES", "SH4", "CO_PAIS", "CO_MUN", "SG_UF_MUN"])
    .agg(vl_fob=("VL_FOB", "sum"), kg=("KG_LIQUIDO", "sum"))
    .reset_index()
)

merged = grupo_perfil.merge(
    mun_perfil,
    left_on=["mes", "sh4", "co_pais"],
    right_on=["CO_MES", "SH4", "CO_PAIS"],
)
merged["bate"] = (merged["vl_fob"] >= TOL * merged["vmle"]) & (
    merged["kg"] >= TOL * merged["peso"]
)

total_combos = grupo_perfil.groupby("grupo").size().rename("total_combos")
bateu = (
    merged[merged["bate"]]
    .groupby(["grupo", "CO_MUN", "SG_UF_MUN"])
    .size()
    .rename("combos_ok")
    .reset_index()
)
bateu = bateu.merge(total_combos, on="grupo")
bateu["cobertura"] = bateu["combos_ok"] / bateu["total_combos"]

candidatos = bateu[bateu["cobertura"] >= 0.9].sort_values(
    ["grupo", "cobertura"], ascending=[True, False]
)
candidatos.to_parquet("gate_1/dados/processado/candidatos_municipio_por_grupo.parquet", index=False)
print(f"grupos com candidato(s) de municipio: {candidatos['grupo'].nunique()} / {df['grupo'].nunique()}")
n_cand = candidatos.groupby("grupo").size()
print(n_cand.describe())
print(candidatos.head(20))
