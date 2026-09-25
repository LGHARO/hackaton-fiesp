"""Crosswalk CO_MUN (Comex Stat, dados/raw/UF_MUN.csv) -> CO_MUNICIPIO (TOM,
usado nos dados abertos de CNPJ da Receita), via nome+UF normalizados.

O codigo numerico CO_MUN_GEO do Comex Stat as vezes diverge do IBGE real
(ex.: Sao Paulo aparece como 3450308 em vez de 3550308) -- por isso o
cruzamento e feito por nome, nao por codigo.
"""
import pandas as pd
from rapidfuzz import fuzz, process

FUZZY_MIN_SCORE = 90


def norm(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.upper()
        .str.strip()
        .str.normalize("NFKD")
        .str.encode("ascii", "ignore")
        .str.decode("ascii")
    )


def build_crosswalk(
    ufmun_csv: str = "shared/dados/raw/UF_MUN.csv",
    tom_csv: str = "shared/dados/raw/tom_ibge_municipios.csv",
) -> pd.DataFrame:
    comex = pd.read_csv(ufmun_csv, sep=";", encoding="latin1", dtype=str)
    comex["nome_n"] = norm(comex["NO_MUN"])

    tom = pd.read_csv(tom_csv, sep=None, engine="python", encoding="latin1")
    tom.columns = ["CO_TOM", "CO_IBGE", "NO_TOM", "NO_IBGE", "UF"]
    tom["nome_n"] = norm(tom["NO_TOM"])

    out = comex.merge(
        tom, left_on=["nome_n", "SG_UF"], right_on=["nome_n", "UF"], how="left"
    )

    falt = out["CO_TOM"].isna()
    for uf, grp in out.loc[falt, ["nome_n", "SG_UF"]].drop_duplicates().groupby("SG_UF"):
        choices = tom.loc[tom["UF"] == uf, "nome_n"]
        if choices.empty:
            continue
        for nome in grp["nome_n"]:
            match = process.extractOne(nome, choices, scorer=fuzz.WRatio)
            if match and match[1] >= FUZZY_MIN_SCORE:
                row = tom.loc[(tom["UF"] == uf) & (tom["nome_n"] == match[0])].iloc[0]
                sel = falt & (out["nome_n"] == nome) & (out["SG_UF"] == uf)
                out.loc[sel, "CO_TOM"] = row["CO_TOM"]

    out["CO_TOM_STR"] = out["CO_TOM"].astype("Int64").astype(str).str.zfill(4)
    return out[["CO_MUN_GEO", "NO_MUN", "SG_UF", "CO_TOM_STR"]].rename(
        columns={"CO_MUN_GEO": "CO_MUN"}
    )


if __name__ == "__main__":
    cw = build_crosswalk()
    sem_match = cw["CO_TOM_STR"].isna() | (cw["CO_TOM_STR"] == "<NA>")
    print(f"{(~sem_match).sum()}/{len(cw)} municipios do Comex Stat casados com a TOM")
    cw.to_parquet("shared/dados/processado/crosswalk_mun_comex_tom.parquet", index=False)
