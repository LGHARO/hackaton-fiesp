"""Passo 4 (gate_2): score final e top 50 CNPJs.

Diferente do gate_1 (onde o grupo vinha da clusterizacao de texto), aqui a
unidade de analise e (municipio, SH4): o municipio ja vem atribuido pela
concentracao geografica publica (passo 3, alta confianca e barato), e SH4
evita misturar produtos de empresas diferentes que por acaso caem na mesma
cidade. Dentro de cada (municipio, SH4), o texto (palavras raras via IDF)
so decide QUAL CNPJ entre os candidatos daquele municipio bate melhor --
o mesmo pre-filtro por substring + rapidfuzz do gate_1, pra nao ter que
fuzzy-matchar contra todo mundo em cidades grandes.
"""
import re
from collections import Counter

import duckdb
import pandas as pd
from rapidfuzz import fuzz

from joblog import log_iteracao

STOP = set(
    "DE DA DO DOS DAS COM PARA EM UM UMA E OU A O AS OS NO NA SEM MAIS ANONIMIZADO "
    "KG UN TIPO QUE PCS SET POR SUA SEU ATE CADA NOME COMERCIAL MARCA LOTE FORMA "
    "PRIMA PRODUTO QUIMICO FISCAL VALOR CODIGO DESCRICAO".split()
)
# nome de municipio brasileiro na descricao costuma ser origem/fabricacao
# ("aco de sorocaba", "vidro de jundiai"), nao marca -- vira falso positivo
# quando bate por acaso com o nome de uma empresa sediada la (ex.: "Sorocaba
# BMX" pareado com peca de rede so por causa da palavra "Sorocaba")
_tom = pd.read_csv(
    "shared/dados/raw/tom_ibge_municipios.csv", sep=None, engine="python", encoding="latin1"
)
STOP |= set(_tom.iloc[:, 2].str.upper().str.split().sum())
MIN_LINHAS = 3
MIN_LOCAL_COUNT = 2
GLOBAL_DF_SAMPLE = 2_000_000
COMPANY_DF_SAMPLE = 1_000_000
COMPANY_DF_MAX = 300  # palavra que aparece em mais de N/1M empresas amostradas
# eh jargao organizacional generico (ex.: "MINISTERIO", "IMPORTADORA",
# "COMERCIO"), nao marca/nome distintivo -- mesmo que seja raro na descricao
# do produto (o que confundiu o IDF sozinho: "MINISTERIO" e raro numa
# descricao de fralda, mas comum em nome de instituicao religiosa)
N_TOP = 50

# causa raiz de varios falsos positivos do primeiro resultado: nada impedia
# um condominio, clube social, igreja ou escritorio de contabilidade de
# "ganhar" o fuzzy match por coincidencia de palavra -- essas entidades nao
# podem estruturalmente ser importadoras comerciais do produto em questao.
# Filtramos pelo CNAE (atividade economica registrada) ANTES do fuzzy match,
# nao depois -- o nome da empresa pode enganar (ex.: "Servicos de Apoio
# Contabil Ltda" cujo CNAE real e reciclagem de sucata de aluminio), o CNAE
# nao. Frases especificas com \b pra nao pegar substring por acidente (ex.:
# "associa" batendo em "beneficiamento associado").
CNAE_NAO_COMERCIAL = re.compile(
    r"\b("
    r"ensino|educa..o|creche|escola|condom.nio|clubes? (social|sociais|esportiv)|"
    r"associa..es?( de| sem)|sindicat|partido pol.tico|administra..o p.blica|"
    r"seguridade social|cart.rios?\b|representa..o consular|embaixada|"
    r"apoio administrativo|escrit.rio.{0,15}contabilidade|"
    r"servi.os.{0,15}contabilidade|advocacia|atividades jur.dicas|"
    r"atividades de apoio . sa.de|atividades hospitalares|cl.nica|"
    r"consult.rio m.dico|fisioterap|cabeleireiro|manicure|esteticista|"
    r"organiza..es religiosas|templo|igreja|entidade religiosa|funer.ria|"
    r"assist.ncia social|transporte escolar"
    r")",
    re.IGNORECASE,
)


def tokens(desc: str) -> list[str]:
    return [w for w in re.findall(r"[A-ZÇÃÕÁÉÍÓÚÂÊÎÔÛ]{4,}", str(desc).upper()) if w not in STOP]


def keywords(descs: pd.Series, global_df: Counter, company_df: Counter, k: int = 6) -> list[str]:
    c = Counter()
    for d in descs:
        c.update(tokens(d))
    candidatos = {
        w: n for w, n in c.items()
        if n >= MIN_LOCAL_COUNT and company_df[w] <= COMPANY_DF_MAX
    }
    ranked = sorted(candidatos, key=lambda w: candidatos[w] / (global_df[w] + 1), reverse=True)
    return ranked[:k]


def main() -> None:
    diag = pd.read_parquet("gate_2/dados/processado/linhas_diagnosticas.parquet")
    est = pd.read_parquet(
        "shared/dados/processado/estabelecimentos_candidatos.parquet",
        columns=["cnpj_basico", "nome_fantasia", "cnae_principal", "municipio"],
    )
    emp = pd.read_parquet(
        "shared/dados/processado/empresas_candidatas.parquet",
        columns=["cnpj_basico", "razao_social"],
    )
    cnaes = pd.read_csv("shared/dados/raw/cnpj/cnaes.csv", dtype=str)
    cnaes_excluidos = set(
        cnaes.loc[cnaes["DESCRICAO"].str.contains(CNAE_NAO_COMERCIAL, na=False), "CO_CNAE"]
    )
    antes = len(est)
    est = est[~est["cnae_principal"].isin(cnaes_excluidos)]
    print(f"filtro de CNAE nao-comercial: {antes - len(est)} estabelecimentos removidos de {antes}")

    empresas = est.merge(emp, on="cnpj_basico", how="inner")
    del est, emp
    empresas["texto"] = (
        empresas["razao_social"].fillna("") + " " + empresas["nome_fantasia"].fillna("")
    ).str.upper()
    print("amostrando nomes de empresa pra frequencia organizacional generica...")
    amostra_nomes = empresas["texto"].sample(
        min(COMPANY_DF_SAMPLE, len(empresas)), random_state=0
    )
    company_df = Counter()
    for t in amostra_nomes:
        company_df.update(set(tokens(t)))
    del amostra_nomes

    por_municipio = dict(tuple(empresas.groupby("municipio")))
    print(f"{len(empresas)} empresas candidatas em {len(por_municipio)} municipios")
    del empresas

    print("amostrando descricoes pra frequencia global (IDF)...")
    con = duckdb.connect()
    amostra = con.sql(
        f"select descricao from read_parquet('gate_2/dados/raw/dados_siscori.pq/*.parquet') "
        f"using sample {GLOBAL_DF_SAMPLE} rows"
    ).df()["descricao"]
    global_df = Counter()
    for d in amostra:
        global_df.update(set(tokens(d)))
    del amostra

    grupos = diag.groupby(["co_tom", "sh4"])
    tam = grupos.size()
    relevantes = tam[tam >= MIN_LINHAS].index
    print(f"{len(relevantes)} grupos (municipio, sh4) com >= {MIN_LINHAS} linhas")

    linhas = []
    for idx, (chave, sub) in enumerate(grupos):
        if chave not in relevantes:
            continue
        if idx % 500 == 0:
            print(f"  processando grupo {idx}...")
        co_tom, sh4 = chave
        with log_iteracao("score_final", f"{co_tom}_{sh4}") as it:
            it["n_linhas"] = len(sub)
            kws = keywords(sub["descricao"], global_df, company_df)
            if not kws:
                it["detalhe"] = "sem palavras-chave"
                continue
            padrao = "|".join(re.escape(w) for w in kws)

            candidatos = por_municipio.get(co_tom)
            if candidatos is None:
                it["detalhe"] = "municipio sem candidatos"
                continue
            hits = candidatos[candidatos["texto"].str.contains(padrao, regex=True, na=False)]
            if hits.empty:
                it["detalhe"] = "nenhum candidato bateu palavra-chave"
                continue

            kw = " ".join(kws)
            fuzzy = hits["texto"].apply(lambda t: fuzz.token_set_ratio(t, kw) / 100)
            top = hits.loc[fuzzy.idxmax()]
            fuzzy_top = fuzzy.max()

            concentracao = sub["concentracao"].iloc[0]
            n_mun = sub["n_mun"].iloc[0]
            n_linhas = len(sub)

            score = 0.35 * concentracao + 0.45 * fuzzy_top + 0.2 * min(n_linhas / 100, 1.0)
            # confianca: baseada em especificidade do match (fuzzy + numero de
            # palavras-chave distintivas), nao no tamanho do municipio -- um match
            # forte numa cidade grande nao e pior so por ter mais concorrentes no
            # pre-filtro (era o erro da versao anterior, punia acertos bons tipo
            # "TE CONNECTIVITY" so por estarem em Sao Paulo)
            confianca = (
                "alta" if fuzzy_top >= 0.85 and len(kws) >= 3
                else "media" if fuzzy_top >= 0.75 and len(kws) >= 2
                else "baixa"
            )
            it["detalhe"] = f"score={score:.3f} confianca={confianca}"
            linhas.append(
                {
                    "co_tom": co_tom,
                    "sh4": sh4,
                    "n_linhas": n_linhas,
                    "n_mun_candidatos": n_mun,
                    "concentracao": concentracao,
                    "cnpj_basico": top["cnpj_basico"],
                    "razao_social": top["razao_social"],
                    "nome_fantasia": top["nome_fantasia"],
                    "fuzzy_score": fuzzy_top,
                    "palavras_chave": kw,
                    "confianca": confianca,
                    "score": score,
                }
            )

    resultado = pd.DataFrame(linhas).sort_values("score", ascending=False)
    resultado.to_parquet("gate_2/dados/processado/palpites_cnpj.parquet", index=False)
    top50 = resultado.head(N_TOP)
    top50.to_csv("gate_2/palpites_cnpj_top50.csv", index=False)
    top50.to_parquet("gate_2/palpites_cnpj_top50.parquet", index=False)
    print(f"{len(resultado)} grupos pontuados; salvando top {N_TOP}")
    print(top50[["co_tom", "sh4", "n_linhas", "cnpj_basico", "razao_social", "confianca", "score"]])


if __name__ == "__main__":
    main()
