"""Passo 6: score final e top 50 CNPJs.

Para cada grupo (provavel importador) com pelo menos MIN_TRANSACOES, pega os
candidatos de CNPJ ativos nos municipios que bateram (passo 3) e rankeia por:
  - cobertura do municipio (passo 3)
  - fuzzy match (rapidfuzz) entre razao_social/nome_fantasia e as palavras
    mais frequentes da descricao do produto do grupo (ex.: marca, "editora",
    "distribuidora" etc.)
  - tamanho do grupo (mais transacoes = mais confianca no perfil)

Cidades grandes (ex. Sao Paulo) tem milhoes de empresas ativas -- fuzzy match
contra todas elas pra cada grupo e inviavel (bilhoes de comparacoes). Por
isso o candidato so entra no rapidfuzz (caro) se ja bateu num pre-filtro
vetorizado por substring (barato, roda em C via pandas.str.contains).
Grupos sem nenhum hit de palavra-chave sao pulados: sem pista lexica, o
match seria essencialmente aleatorio.

Saida: 50 chutes de CNPJ (CNPJ_BASICO, 8 digitos -- a raiz, sem filial/DV),
um por grupo, para os grupos com maior confianca.
"""
import re
from collections import Counter

import pandas as pd
from rapidfuzz import fuzz

STOP = set(
    "DE DA DO DOS DAS COM PARA EM UM UMA E OU A O AS OS NO NA SEM MAIS ANONIMIZADO "
    "KG UN TIPO QUE PCS SET POR SUA SEU ATE CADA".split()
)
MIN_TRANSACOES = 3
MAX_CANDIDATOS_MUNICIPIO = 5
MIN_LOCAL_COUNT = 2
N_TOP = 50


def tokens(desc: str) -> list[str]:
    return [w for w in re.findall(r"[A-ZÇÃÕÁÉÍÓÚÂÊÎÔÛ]{4,}", str(desc).upper()) if w not in STOP]


def keywords(descs: pd.Series, global_df: Counter, k: int = 6) -> list[str]:
    """Palavras frequentes NO GRUPO mas raras no resto da base (tipo IDF) --
    isso evita jargao generico de declaracao aduaneira (NOME, COMERCIAL,
    MARCA, LOTE, FORMA, PRIMA...) que aparece em quase toda descricao e nao
    tem nenhum poder discriminativo (nome de marca/empresa de verdade e raro
    no resto do corpus)."""
    c = Counter()
    for d in descs:
        c.update(tokens(d))
    candidatos = {w: n for w, n in c.items() if n >= MIN_LOCAL_COUNT}
    ranked = sorted(candidatos, key=lambda w: candidatos[w] / global_df[w], reverse=True)
    return ranked[:k]


def main() -> None:
    df = pd.read_parquet("gate_1/dados/processado/df_clusterizado.parquet")
    cand_mun = pd.read_parquet("gate_1/dados/processado/candidatos_municipio_por_grupo.parquet")
    est = pd.read_parquet("shared/dados/processado/estabelecimentos_candidatos.parquet")
    emp = pd.read_parquet("shared/dados/processado/empresas_candidatas.parquet")

    empresas = est.merge(emp, on="cnpj_basico", how="inner")
    empresas["texto"] = (
        empresas["razao_social"].fillna("") + " " + empresas["nome_fantasia"].fillna("")
    ).str.upper()
    por_municipio = dict(tuple(empresas.groupby("municipio")))
    print(f"{len(empresas)} empresas candidatas em {len(por_municipio)} municipios")

    grupo_size = df.groupby("grupo").size().rename("n")
    n_cand = cand_mun.groupby("grupo").size()
    grupos_relevantes = grupo_size[
        (grupo_size >= MIN_TRANSACOES)
        & (grupo_size.index.isin(n_cand[n_cand <= MAX_CANDIDATOS_MUNICIPIO].index))
    ].index
    global_df = Counter()
    for d in df["descricao_do_produto"]:
        global_df.update(set(tokens(d)))

    grupo_kw = (
        df[df["grupo"].isin(grupos_relevantes)]
        .groupby("grupo")["descricao_do_produto"]
        .apply(lambda descs: keywords(descs, global_df))
    )
    print(
        f"{len(grupos_relevantes)} grupos com >= {MIN_TRANSACOES} transacoes "
        f"e <= {MAX_CANDIDATOS_MUNICIPIO} municipios candidatos"
    )

    linhas = []
    grupos_a_processar = cand_mun[cand_mun["grupo"].isin(grupos_relevantes)].groupby("grupo")
    for idx, (grupo, sub) in enumerate(grupos_a_processar):
        if idx % 100 == 0:
            print(f"  processando grupo {idx}/{len(grupos_relevantes)}...")
        kws = grupo_kw.get(grupo, [])
        if not kws:
            continue
        padrao = "|".join(re.escape(w) for w in kws)

        partes = [por_municipio[m] for m in sub["CO_TOM_STR"] if m in por_municipio]
        if not partes:
            continue
        candidatos = pd.concat(partes, ignore_index=True) if len(partes) > 1 else partes[0]

        hits = candidatos[candidatos["texto"].str.contains(padrao, regex=True, na=False)]
        if hits.empty:
            continue

        kw = " ".join(kws)
        fuzzy = hits["texto"].apply(lambda t: fuzz.token_set_ratio(t, kw) / 100)
        top = hits.loc[fuzzy.idxmax()]
        fuzzy_top = fuzzy.max()

        n_hits = len(hits)
        confianca = (
            "alta" if fuzzy_top >= 0.85 and len(kws) >= 3
            else "baixa" if n_hits > 20 or len(kws) < 2
            else "media"
        )

        melhor_cobertura = sub["cobertura"].max()
        score = 0.5 * melhor_cobertura + 0.4 * fuzzy_top + 0.1 * min(
            grupo_size[grupo] / 500, 1.0
        )
        linhas.append(
            {
                "grupo": grupo,
                "n_transacoes": grupo_size[grupo],
                "cobertura_municipio": melhor_cobertura,
                "cnpj_basico": top["cnpj_basico"],
                "razao_social": top["razao_social"],
                "nome_fantasia": top["nome_fantasia"],
                "confianca": confianca,
                "fuzzy_score": fuzzy_top,
                "palavras_chave": kw,
                "score": score,
            }
        )

    resultado = pd.DataFrame(linhas).sort_values("score", ascending=False)
    resultado.to_parquet("gate_1/dados/processado/palpites_cnpj.parquet", index=False)
    top50 = resultado.head(N_TOP)
    top50.to_csv("gate_1/palpites_cnpj_top50.csv", index=False)
    top50.to_parquet("gate_1/palpites_cnpj_top50.parquet", index=False)
    print(f"{len(resultado)} grupos com candidato pontuado; salvando top {N_TOP}")
    print(top50[["grupo", "n_transacoes", "cnpj_basico", "razao_social", "score"]])


if __name__ == "__main__":
    main()
