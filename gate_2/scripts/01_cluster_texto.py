"""Clusterizacao de texto para a base de 23,2M linhas (dados/dados_siscori.pq).

Sem chave de ligacao entre linhas (chave_item e ~unico por linha, ao contrario
do numero_de_ordem da base menor) -- o "grupo" final e so o cluster de texto,
sem passo de uniao via grafo.

23M linhas / 10,5M descricoes unicas inteiras seria inviavel pro HDBSCAN de
uma vez so. Bloqueamos por NCM (8 digitos): um cluster de "perfume" nunca vai
se confundir com um de "parafuso" mesmo sem blocking, entao blocar por NCM e
semanticamente correto E reduz cada chamada de clustering pra um problema
pequeno.

90 dos 5756 blocos de NCM (autopecas, parafusos, plastico -- categorias
genericas de altissimo volume) tem entre 20 mil e 258 mil descricoes unicas
mesmo depois do blocking e cobrem mais da metade das linhas da base. HDBSCAN
nesses e caro demais; usamos MiniBatchKMeans (O(n), streaming) neles.
Ponytail: MiniBatchKMeans da clusters menos "limpos" que HDBSCAN (nao separa
ruido explicitamente, k e um chute heuristico) -- trocar por HDBSCAN nesses
blocos tambem se, medido, a qualidade dos clusters grandes for baixa demais.

Os 5666 blocos pequenos tem custo dominado por OVERHEAD FIXO por bloco
(~1.5s de setup do TF-IDF/SVD), nao pelo volume -- rodar sequencial estimava
~6h. Cada bloco e independente (embaraçosamente paralelo), entao processamos
com ProcessPoolExecutor em vez de laco serial.
"""

import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN, MiniBatchKMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from joblog import log_iteracao

SRC = "gate_2/dados/raw/dados_siscori.pq/*.parquet"
OUT_DIR = Path("gate_2/dados/processado/cluster_parts")
MAX_HDBSCAN = 20_000  # acima disso, MiniBatchKMeans
N_WORKERS = 1  # RAM-limited (16GB total, so ~6-7GB livre com o resto do sistema
# aberto): 10, depois 4, depois 3 workers -- todos estouraram a RAM quando blocos
# grandes (ate 257k desc unicas, ~1.5GB cada) coincidiram. Sequencial e mais lento
# mas nao trava a maquina do usuario -- ponytail: voltar a paralelizar so com
# mais RAM disponivel ou isolando os blocos grandes numa fila propria
VEC = {
    "analyzer": "char_wb",
    "ngram_range": (3, 5),
    "min_df": 2,
    "max_features": 60_000,  # reduzido de 200k pra caber a RAM (ver nota acima)
    "strip_accents": "unicode",
    "sublinear_tf": True,
}
SVD_COMPONENTS = 80  # reduzido de 100


def cluster_bloco(descs: np.ndarray) -> np.ndarray:
    uniq, inv = np.unique(descs, return_inverse=True)
    if len(uniq) < 5:
        return np.arange(len(uniq))[
            inv
        ]  # bloco minusculo: cada descricao unica vira grupo

    X = TfidfVectorizer(**VEC).fit_transform(uniq)
    Z = normalize(
        TruncatedSVD(min(SVD_COMPONENTS, X.shape[1] - 1), random_state=0).fit_transform(X)
    )

    if len(uniq) <= MAX_HDBSCAN:
        labels = HDBSCAN(min_cluster_size=5, min_samples=3).fit_predict(Z)
        noise = labels == -1
        labels = labels.astype(object)
        labels[noise] = ["r" + str(i) for i in np.nonzero(noise)[0]]
    else:
        k = min(max(len(uniq) // 20, 100), 8000)
        labels = MiniBatchKMeans(n_clusters=k, random_state=0, n_init=1).fit_predict(Z)

    return pd.factorize(labels)[0][inv]


def processar_bloco(ncm: str) -> tuple[str, int, float]:
    os.environ.setdefault(
        "OMP_NUM_THREADS", "1"
    )  # evita oversubscription entre workers
    if ncm is None:
        return ncm, -1, 0.0  # linhas de ncm nulo (lixo/incompleto) -- ignora
    parte = OUT_DIR / f"ncm_{ncm}.parquet"
    t0 = time.time()
    if parte.exists():
        return ncm, -1, 0.0

    with log_iteracao("cluster_texto", ncm) as it:
        con = duckdb.connect()
        df = con.sql(
            f"select chave_item, descricao from read_parquet('{SRC}') where ncm = '{ncm}'"
        ).df()
        df["grupo_local"] = cluster_bloco(df["descricao"].fillna("").str.lower().to_numpy())
        df[["chave_item", "grupo_local"]].to_parquet(parte, index=False)
        it["n_linhas"] = len(df)
    return ncm, len(df), time.time() - t0


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    blocos = (
        con.sql(f"select distinct ncm from read_parquet('{SRC}') order by ncm")
        .df()["ncm"]
        .tolist()
    )
    pendentes = [b for b in blocos if not (OUT_DIR / f"ncm_{b}.parquet").exists()]
    print(
        f"{len(blocos)} blocos de NCM, {len(pendentes)} pendentes, {N_WORKERS} workers",
        flush=True,
    )

    t0 = time.time()
    feitos = 0
    with ProcessPoolExecutor(max_workers=N_WORKERS) as ex:
        futuros = {ex.submit(processar_bloco, ncm): ncm for ncm in pendentes}
        for fut in as_completed(futuros):
            ncm, n, dt = fut.result()
            feitos += 1
            if feitos % 100 == 0 or dt > 30:
                decorrido = time.time() - t0
                print(
                    f"  [{feitos}/{len(pendentes)}] ncm={ncm} linhas={n} "
                    f"({dt:.1f}s bloco, {decorrido / 60:.1f}min decorridos)",
                    flush=True,
                )

    print("consolidando...", flush=True)
    partes = []
    for p in OUT_DIR.glob("ncm_*.parquet"):
        d = pd.read_parquet(p)
        d["ncm"] = p.stem.removeprefix("ncm_")
        partes.append(d)
    resultado = pd.concat(partes, ignore_index=True)
    chave = resultado["ncm"].astype(str) + "_" + resultado["grupo_local"].astype(str)
    resultado["grupo"] = pd.factorize(chave)[0]
    resultado[["chave_item", "grupo"]].to_parquet(
        "gate_2/dados/processado/texto_clusterizado.parquet", index=False
    )
    print(f"total: {len(resultado)} linhas, {resultado['grupo'].nunique()} grupos")


if __name__ == "__main__":
    main()
