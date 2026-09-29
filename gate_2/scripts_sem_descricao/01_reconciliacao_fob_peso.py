"""Passo 1 (Base 2): Reconciliacao aduaneira exata por SH4, FOB e Peso Liquido.

Cruza linhas atomicas (n_linhas = 1) da Base 2 com agregacoes municipais
do Comex Stat (IMP_2021_MUN.csv) onde apenas 1 municipio movimentou o combo.
"""
from pathlib import Path
import sys
import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))
from mapa_paises import build_mapa

SRC_BASE2 = "gate_2/dados/raw/dados_siscori_sem_desc.pq/*.parquet"
SRC_COMEX = "shared/dados/raw/IMP_2021_MUN.csv"
OUT_DIR = Path("gate_2/dados/processado_sem_desc")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    con = duckdb.connect()

    # 1. Agregado publico municipal (Comex Stat opera em SH4)
    con.sql(f"""
        create view comex_mun as
        select
            cast(CO_MES as integer) as mes,
            lpad(cast(SH4 as varchar), 4, '0') as sh4,
            cast(CO_PAIS as integer) as co_pais,
            cast(CO_MUN as integer) as co_mun,
            SG_UF_MUN as uf,
            sum(VL_FOB) as fob_pub,
            sum(KG_LIQUIDO) as kg_pub
        from read_csv('{SRC_COMEX}', delim=';', encoding='latin-1')
        group by 1, 2, 3, 4, 5
    """)

    # 2. Mapeamento de paises (correcao de tipo DataFrame)
    paises = con.sql(f"""
        select distinct pais_origem 
        from read_parquet('{SRC_BASE2}') 
        where pais_origem is not null
    """).df()
    mapa_pais = build_mapa(paises["pais_origem"])
    mapa_df = pd.DataFrame(list(mapa_pais.items()), columns=["pais_origem", "co_pais"])
    con.register("mapa_pais", mapa_df)

    # 3. Crosswalk TOM padronizado
    con.sql("""
        create view crosswalk_tom as
        select 
            cast(CO_MUN as integer) as co_mun,
            lpad(cast(CO_TOM_STR as varchar), 4, '0') as co_tom
        from read_parquet('shared/dados/processado/crosswalk_mun_comex_tom.parquet')
    """)

    # 4. Agrupamento da Base 2: isolando combos com exatamente 1 linha (atomicos)
    con.sql(f"""
        create view base2_agrupada as
        select
            cast(substr(periodo, 6, 2) as integer) as mes,
            substr(lpad(cast(ncm as varchar), 8, '0'), 1, 4) as sh4,
            cast(m.co_pais as integer) as co_pais,
            count(*) as n_linhas,
            min(chave_item) as chave_item,
            sum(try_cast(replace(vmle_dolar, ',', '.') as double)) as fob_base2,
            sum(try_cast(replace(peso_liquido, ',', '.') as double)) as peso_base2
        from read_parquet('{SRC_BASE2}') b
        join mapa_pais m using (pais_origem)
        group by 1, 2, 3
        having count(*) = 1
    """)

    # 5. Join com tolerÃ¢ncia <= 1.0 (USD e KG) e unicidade municipal estrita
    print("Executando reconciliacao de duplo balanco (FOB + Peso)...")
    resultado = con.sql("""
        with candidatos as (
            select
                b.mes,
                b.sh4,
                b.co_pais,
                b.chave_item,
                b.fob_base2,
                b.peso_base2,
                c.co_mun,
                c.uf,
                c.fob_pub,
                c.kg_pub,
                ct.co_tom,
                count(distinct c.co_mun) over (partition by b.mes, b.sh4, b.co_pais) as n_mun_distintos
            from base2_agrupada b
            join comex_mun c
                on b.mes = c.mes
                and b.sh4 = c.sh4
                and b.co_pais = c.co_pais
                and abs(b.fob_base2 - c.fob_pub) <= 1.0
                and abs(b.peso_base2 - c.kg_pub) <= 1.0
            left join crosswalk_tom ct on ct.co_mun = c.co_mun
        )
        select *
        from candidatos
        where n_mun_distintos = 1 and co_tom is not null
    """).df()

    saida = OUT_DIR / "matches_aduaneiros_exatos.parquet"
    resultado.to_parquet(saida, index=False)
    print(f"Linhas unÃ­vocas reconciliadas com sucesso: {len(resultado)}")


if __name__ == "__main__":
    main()
