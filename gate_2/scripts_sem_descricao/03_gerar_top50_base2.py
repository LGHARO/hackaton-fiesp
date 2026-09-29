"""Passo 3 (Base 2): Ranqueamento e Selecao dos Top 50 Palpites via DuckDB (Otimizado)."""
from pathlib import Path
import duckdb

DIR_PROC = Path("gate_2/dados/processado_sem_desc")
OUT_DIR = Path("gate_2")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    con = duckdb.connect()
    con.sql("SET preserve_insertion_order = false;")

    # 1. Carregar os matches do Passo 1
    con.sql(f"""
        create view matches as 
        select 
            chave_item,
            lpad(cast(co_tom as varchar), 4, '0') as co_tom,
            fob_base2
        from read_parquet('{DIR_PROC}/matches_aduaneiros_exatos.parquet')
    """)

    # 2. Carregar as empresas tratadas
    con.sql(f"""
        create view empresas as 
        select 
            cnpj_basico,
            cnpj_completo,
            razao_social,
            lpad(cast(municipio as varchar), 4, '0') as municipio,
            qtd_raizes_no_mun
        from read_parquet('{DIR_PROC}/empresas_candidatas_tratadas.parquet')
    """)

    # 3. Filtrar apenas os municipios com menor dispersao presentes nos matches (top 150 para garantir 50 unicos)
    con.sql("""
        create temp table top_municipios as
        select distinct
            m.co_tom,
            e.qtd_raizes_no_mun
        from matches m
        inner join (
            select distinct municipio, qtd_raizes_no_mun 
            from empresas
        ) e on m.co_tom = e.municipio
        order by e.qtd_raizes_no_mun asc
        limit 150
    """)

    # 4. Cruzamento restrito apenas nos municipios mais concentrados (evita explosao de disco e memoria)
    top50 = con.sql("""
        with candidatos as (
            select 
                m.chave_item,
                e.cnpj_basico,
                e.cnpj_completo,
                e.razao_social,
                e.qtd_raizes_no_mun,
                (1.0 / cast(e.qtd_raizes_no_mun as double)) as score_monopolio,
                m.fob_base2
            from matches m
            inner join top_municipios tm on m.co_tom = tm.co_tom
            inner join empresas e on m.co_tom = e.municipio
        ),
        dedupe_cnpj as (
            select *
            from candidatos
            qualify row_number() over (
                partition by cnpj_basico 
                order by score_monopolio desc, fob_base2 desc
            ) = 1
        ),
        dedupe_item as (
            select *
            from dedupe_cnpj
            qualify row_number() over (
                partition by chave_item 
                order by score_monopolio desc, fob_base2 desc
            ) = 1
        )
        select *
        from dedupe_item
        order by score_monopolio desc, fob_base2 desc
        limit 50
    """).df()

    entrega = top50[["chave_item", "cnpj_completo"]].rename(columns={"cnpj_completo": "CNPJ"})
    entrega["CNPJ"] = entrega["CNPJ"].astype(str).str.zfill(14)

    assert len(entrega) <= 50, "Erro: ultrapassou 50 palpites"
    assert (entrega["CNPJ"].str.len() == 14).all(), "Erro: CNPJs fora do formato de 14 digitos"

    saida = OUT_DIR / "palpites_base2_top50.csv"
    entrega.to_csv(saida, index=False)
    top50.to_parquet(OUT_DIR / "palpites_base2_top50_detalhado.parquet", index=False)

    print(f"Top 50 gerado com sucesso: {saida}")
    print(f"Total de palpites gerados: {len(entrega)}")
    print(f"Menor concorrencia municipal no Top 50: {top50['qtd_raizes_no_mun'].min()} empresa(s) no municipio")
    print(f"Maior concorrencia municipal no Top 50: {top50['qtd_raizes_no_mun'].max()} empresa(s) no municipio")


if __name__ == "__main__":
    main()
