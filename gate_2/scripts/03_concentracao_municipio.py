"""Passo 3 (gate_2) -- sinal primario: concentracao geografica publica.

Em vez de depender da clusterizacao de texto (fragil sem chave de ligacao
entre linhas -- ver gate_2/scripts/01_cluster_texto.py), exploramos uma
estrutura que ja existe nos dados publicos do Comex Stat, independente da
nossa base: pra muitas combinacoes (mes, SH4, pais de origem), quase toda a
importacao nacional daquele nicho passa por UM municipio so (polo/porto
especializado). Isso da atribuicao de municipio de graca pra qualquer linha
nossa que caia numa combinacao "diagnostica" -- sem clusterizar nada.

Achado empirico (ver conversa): de ~211 mil combos (mes,sh4,pais), 41% tem
>=99% da FOB nacional concentrada em 1 municipio. Isso cobre ~1,74 milhao
das 23,2 milhoes de linhas da base (7,5%) com sinal forte e barato.
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))
from mapa_paises import build_mapa  # noqa: E402

SRC = "gate_2/dados/raw/dados_siscori.pq/*.parquet"
CONCENTRACAO_MIN = 0.99
MAX_MUNICIPIOS = 3  # aceita ate 3 municipios candidatos por combo


def main() -> None:
    con = duckdb.connect()

    con.sql(
        f"""
        create view mun_base as
        select
            cast(CO_MES as integer) as mes,
            cast(SH4 as integer) as sh4,
            cast(CO_PAIS as integer) as co_pais,
            CO_MUN as co_mun, SG_UF_MUN as uf,
            sum(VL_FOB) as fob
        from read_csv('shared/dados/raw/IMP_2021_MUN.csv', delim=';', encoding='latin-1')
        group by 1, 2, 3, 4, 5
        """
    )
    con.sql(
        """
        create view mun_tot as
        select mes, sh4, co_pais, sum(fob) as fob_total, count(distinct co_mun) as n_mun
        from mun_base group by 1, 2, 3
        """
    )
    con.sql(
        """
        create view mun_top1 as
        select mes, sh4, co_pais, co_mun, uf, fob as fob_top1,
               row_number() over (partition by mes, sh4, co_pais order by fob desc) as rk
        from mun_base
        """
    )
    con.sql(
        f"""
        create view combos_diagnosticos as
        select t.mes, t.sh4, t.co_pais, t.n_mun, t.fob_total,
               m1.co_mun, m1.uf, m1.fob_top1,
               m1.fob_top1::double / t.fob_total as concentracao
        from mun_tot t join mun_top1 m1 using (mes, sh4, co_pais)
        where m1.rk = 1
              and m1.fob_top1::double / t.fob_total >= {CONCENTRACAO_MIN}
              and t.n_mun <= {MAX_MUNICIPIOS}
        """
    )

    paises = con.sql(
        f"select distinct pais_origem from read_parquet('{SRC}') where pais_origem is not null"
    ).df()
    mapa_pais = build_mapa(paises["pais_origem"])
    mapa_df = pd.DataFrame({"pais_origem": mapa_pais.keys(), "co_pais": mapa_pais.values()})
    con.register("mapa_pais", mapa_df)

    cw = pd.read_parquet("shared/dados/processado/crosswalk_mun_comex_tom.parquet")
    cw["CO_MUN"] = cw["CO_MUN"].astype(int)
    con.register("crosswalk_tom", cw[["CO_MUN", "CO_TOM_STR"]])

    resultado = con.sql(
        """
        select
            b.chave_item, b.descricao,
            cd.sh4, cd.co_mun, cd.uf, cd.concentracao, cd.n_mun,
            ct.CO_TOM_STR as co_tom
        from read_parquet($src) b
        join mapa_pais m using (pais_origem)
        join combos_diagnosticos cd
            on cd.mes = cast(substr(b.periodo, 6, 2) as integer)
            and cd.sh4 = cast(substr(b.ncm, 1, 4) as integer)
            and cd.co_pais = cast(m.co_pais as integer)
        left join crosswalk_tom ct on ct.CO_MUN = cd.co_mun
        """,
        params={"src": SRC},
    ).df()

    Path("gate_2/dados/processado").mkdir(parents=True, exist_ok=True)
    resultado.to_parquet("gate_2/dados/processado/linhas_diagnosticas.parquet", index=False)
    print(f"{len(resultado)} linhas atribuidas via concentracao geografica")
    print(f"municipios distintos: {resultado['co_mun'].nunique()}")
    print(f"sem crosswalk TOM: {resultado['co_tom'].isna().sum()}")


if __name__ == "__main__":
    main()
