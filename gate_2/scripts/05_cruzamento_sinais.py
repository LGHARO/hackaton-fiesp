"""Passo 5 (gate_2): cruza o sinal primario (concentracao geografica, passo 4)
com o sinal secundario (clusterizacao de texto, passo 1).

Para cada grupo pontuado (municipio, SH4), verifica se as linhas
diagnosticas que apontaram pra aquele municipio TAMBEM caem, majoritariamente,
no MESMO cluster de texto. Se sim, e uma confirmacao independente (duas
fontes de evidencia diferentes concordando). Se as linhas estao espalhadas
em varios clusters de texto distintos, e um sinal de alerta: pode ser mais
de uma empresa diferente sendo somada no mesmo (municipio, SH4).
"""
import pandas as pd

from joblog import log_iteracao


def main() -> None:
    diag = pd.read_parquet("gate_2/dados/processado/linhas_diagnosticas.parquet")
    cluster = pd.read_parquet("gate_2/dados/processado/texto_clusterizado.parquet")
    palpites = pd.read_parquet("gate_2/dados/processado/palpites_cnpj.parquet")

    diag_cluster = diag.merge(cluster, on="chave_item", how="left")

    linhas = []
    for _, row in palpites.iterrows():
        with log_iteracao("cruzamento_sinais", f"{row['co_tom']}_{row['sh4']}") as it:
            sub = diag_cluster[
                (diag_cluster["co_tom"] == row["co_tom"]) & (diag_cluster["sh4"] == row["sh4"])
            ]
            it["n_linhas"] = len(sub)
            if sub.empty or sub["grupo"].isna().all():
                concordancia = None
                maior_cluster_n = None
            else:
                contagem = sub["grupo"].value_counts()
                maior_cluster_n = int(contagem.iloc[0])
                concordancia = maior_cluster_n / len(sub)
            linhas.append(
                {**row.to_dict(), "concordancia_cluster": concordancia, "maior_cluster_n": maior_cluster_n}
            )

    resultado = pd.DataFrame(linhas)
    resultado["score_final"] = resultado["score"] + 0.1 * resultado["concordancia_cluster"].fillna(0)

    # ranking final: confianca primeiro, score so como desempate dentro do
    # mesmo nivel. So existem 55 grupos alta/media no total (contra 4203
    # baixa) -- sem isso, "baixa" com score inflado pela concordancia de
    # cluster desalojava 48 dos 55 alta/media do top 50.
    ordem_confianca = {"alta": 0, "media": 1, "baixa": 2}
    resultado["_ordem"] = resultado["confianca"].map(ordem_confianca)
    resultado = resultado.sort_values(["_ordem", "score_final"], ascending=[True, False]).drop(
        columns="_ordem"
    )
    resultado.to_parquet("gate_2/dados/processado/palpites_cnpj_cruzado.parquet", index=False)
    resultado.head(50).to_csv("gate_2/palpites_cnpj_top50_final.csv", index=False)
    resultado.head(50).to_parquet("gate_2/palpites_cnpj_top50_final.parquet", index=False)
    print(f"concordancia media: {resultado['concordancia_cluster'].mean():.2f}")
    print(
        resultado[
            ["co_tom", "sh4", "razao_social", "confianca", "concordancia_cluster", "score_final"]
        ].head(20)
    )


if __name__ == "__main__":
    main()
