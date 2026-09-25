"""Baixa Estabelecimentos{0..9}.zip da Receita (streaming), filtra so as linhas
ATIVAS cujo municipio (codigo TOM) esta na lista de candidatos do passo 3, e
descarta o zip -- evita guardar os ~20GB descompactados no disco.

So mantem as colunas necessarias pro score (passo 6): filtrar por municipio
sozinho quase nao reduz o volume (os municipios candidatos concentram a
maior parte dos CNPJs do pais), entao o corte real vem de situacao=ATIVA +
descartar colunas irrelevantes (telefone, email, endereco...). Cada arquivo
e salvo em disco assim que processado, pra nao acumular tudo em RAM.
"""
import zipfile
from pathlib import Path

import pandas as pd
import requests

BASE = "https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/2026-09-14"
COLS = [
    "cnpj_basico", "cnpj_ordem", "cnpj_dv", "matriz_filial", "nome_fantasia",
    "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao_cadastral",
    "cidade_exterior", "pais", "data_inicio_atividade", "cnae_principal",
    "cnae_secundaria", "tipo_logradouro", "logradouro", "numero", "complemento",
    "bairro", "cep", "uf", "municipio", "ddd1", "telefone1", "ddd2", "telefone2",
    "ddd_fax", "fax", "email", "situacao_especial", "data_situacao_especial",
]
MANTER = ["cnpj_basico", "nome_fantasia", "cnae_principal", "uf", "municipio"]
ATIVA = "02"
RAW_DIR = Path("shared/dados/raw/cnpj")
PARTS_DIR = Path("shared/dados/processado/estab_parts")
OUT_DIR = Path("shared/dados/processado")
CANDIDATOS_MUNICIPIO = Path("gate_1/dados/processado/candidatos_municipio_por_grupo.parquet")


def alvo_municipios() -> set[str]:
    c = pd.read_parquet(CANDIDATOS_MUNICIPIO)
    return set(c["CO_TOM_STR"].dropna().unique())


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
    alvo = alvo_municipios()
    print(f"filtrando por {len(alvo)} municipios (codigo TOM)")

    for i in range(10):
        nome = f"Estabelecimentos{i}.zip"
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
                    dtype=str, chunksize=300_000,
                    usecols=["cnpj_basico", "nome_fantasia", "situacao_cadastral",
                             "cnae_principal", "uf", "municipio"],
                ):
                    bate = (chunk["situacao_cadastral"] == ATIVA) & chunk["municipio"].isin(alvo)
                    partes_chunk.append(chunk.loc[bate, MANTER])

        dest.unlink()  # descarta o zip (2-4GB) assim que filtrado
        pd.concat(partes_chunk, ignore_index=True).to_parquet(parte, index=False)
        print(f"  {nome}: {sum(len(x) for x in partes_chunk)} linhas ativas nos municipios alvo")

    resultado = pd.concat(
        (pd.read_parquet(p) for p in sorted(PARTS_DIR.glob("parte*.parquet"))),
        ignore_index=True,
    )
    resultado.to_parquet(OUT_DIR / "estabelecimentos_candidatos.parquet", index=False)
    print(f"total final: {len(resultado)} estabelecimentos ativos nos municipios candidatos")


if __name__ == "__main__":
    main()
