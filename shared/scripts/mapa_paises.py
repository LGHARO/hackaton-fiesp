"""Mapa pais_de_origem (nome livre, pt-br) -> CO_PAIS (Comex Stat).
Casamento exato por nome normalizado; residuo por fuzzy match (rapidfuzz).
"""
import pandas as pd
from rapidfuzz import fuzz, process

MANUAL = {
    "FORMOSA (TAIWAN)": "161",  # Taiwan (Formosa)
}
FUZZY_MIN_SCORE = 75


def norm(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.upper()
        .str.strip()
        .str.normalize("NFKD")
        .str.encode("ascii", "ignore")
        .str.decode("ascii")
        .str.replace(r",.*", "", regex=True)
        .str.replace(r"\(.*\)", "", regex=True)
        .str.strip()
    )


def build_mapa(nomes_origem: pd.Series, pais_csv: str = "shared/dados/raw/PAIS.csv") -> dict:
    pais = pd.read_csv(pais_csv, sep=";", dtype=str, encoding="latin1")
    pn = norm(pais["NO_PAIS"])
    exato = dict(zip(pn, pais["CO_PAIS"]))
    choices = list(pn)

    origem_norm = norm(nomes_origem).drop_duplicates()
    mapa = {}
    for nome_raw, nome in zip(nomes_origem.drop_duplicates(), origem_norm):
        if nome_raw.upper().strip() in MANUAL:
            mapa[nome_raw] = MANUAL[nome_raw.upper().strip()]
        elif nome in exato:
            mapa[nome_raw] = exato[nome]
        else:
            match, score, _ = process.extractOne(nome, choices, scorer=fuzz.WRatio)
            mapa[nome_raw] = exato[match] if score >= FUZZY_MIN_SCORE else None
    return mapa


if __name__ == "__main__":
    df = pd.read_parquet("gate_1/dados/processado/df_clusterizado.parquet")
    mapa = build_mapa(df["pais_de_origem"])
    sem_match = [k for k, v in mapa.items() if v is None]
    print(f"{len(mapa) - len(sem_match)}/{len(mapa)} nomes de pais casados")
    print("sem match:", sem_match)
