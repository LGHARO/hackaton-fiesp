"""Baixa Empresas{0..9}.zip da Receita (streaming), filtra so as linhas cujo
cnpj_basico esta entre os estabelecimentos candidatos (municipio bateu no
passo 3) -- razao social e porte vem daqui, nao de Estabelecimentos.
"""
import zipfile
from pathlib import Path

import pandas as pd
import requests

BASE = "https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/2026-09-14"
COLS = [
    "cnpj_basico", "razao_social", "natureza_juridica",
    "qualificacao_responsavel", "capital_social", "porte", "ente_federativo",
]
RAW_DIR = Path("shared/dados/raw/cnpj")
PARTS_DIR = Path("shared/dados/processado/emp_parts")
OUT_DIR = Path("shared/dados/processado")
MANTER = ["cnpj_basico", "razao_social", "porte"]


def baixar(nome: str, dest: Path) -> None:
    if dest.exists():
        return
    with requests.get(f"{BASE}/{nome}", stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    est = pd.read_parquet(OUT_DIR / "estabelecimentos_candidatos.parquet")
    alvo = set(est["cnpj_basico"].unique())
    print(f"filtrando por {len(alvo)} cnpj_basico candidatos")

    for i in range(10):
        nome = f"Empresas{i}.zip"
        parte = PARTS_DIR / f"parte{i}.parquet"
        if parte.exists():
            print(f"{nome}: ja processado, pulando")
            continue

        dest = RAW_DIR / nome
        print(f"baixando {nome}...")
        baixar(nome, dest)

        partes_chunk = []
        with zipfile.ZipFile(dest) as z:
            inner = z.namelist()[0]
            with z.open(inner) as f:
                for chunk in pd.read_csv(
                    f, sep=";", encoding="latin1", header=None, names=COLS,
                    dtype=str, chunksize=300_000, usecols=MANTER,
                ):
                    partes_chunk.append(chunk[chunk["cnpj_basico"].map(alvo.__contains__)])

        dest.unlink()
        pd.concat(partes_chunk, ignore_index=True).to_parquet(parte, index=False)
        print(f"  {nome}: {sum(len(x) for x in partes_chunk)} linhas filtradas")

    resultado = pd.concat(
        (pd.read_parquet(p) for p in sorted(PARTS_DIR.glob("parte*.parquet"))),
        ignore_index=True,
    )
    resultado.to_parquet(OUT_DIR / "empresas_candidatas.parquet", index=False)
    print(f"total final: {len(resultado)} empresas candidatas")


if __name__ == "__main__":
    main()
