#!/usr/bin/env python3
"""
Script para download e indexação dos dados oficiais do Comex Stat (MDIC).
Baixa a base bruta de importações de 2021 (IMP_2021.csv), filtra os NCMs presentes
na base de operações do hackathon e gera uma tabela de referência compacta mapeando:
    (NCM, Mês) -> UFs importadoras
    NCM -> UFs importadoras no ano
"""

import os
import sys
import ssl
import time
import urllib.request
import pandas as pd

COMEX_URL = "https://balanca.mdic.gov.br/balanca/bd/comexstat-bd/ncm/IMP_2021.csv"
OUTPUT_PARQUET = "data/reference/comexstat_2021_ncm_uf.parquet"
OPS_FILE = "data/processed/operacoes_processadas.parquet"

def main():
    os.makedirs("data/reference", exist_ok=True)
    os.makedirs("data/raw", exist_ok=True)

    # 1. Obter NCMs únicos da base de operações
    target_ncms = set()
    if os.path.exists(OPS_FILE):
        df_ops = pd.read_parquet(OPS_FILE, columns=["cod_ncm"])
        target_ncms = set(df_ops["cod_ncm"].dropna().astype(str).str.strip().unique())
        print(f"Total de NCMs-alvo na base de operações: {len(target_ncms):,}")

    raw_csv = "data/raw/IMP_2021.csv"
    if not os.path.exists(raw_csv):
        print(f"Baixando dados oficiais do Comex Stat 2021 ({COMEX_URL})...")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(COMEX_URL, headers={"User-Agent": "Mozilla/5.0"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120, context=ctx) as resp, open(raw_csv, "wb") as out_f:
            chunk_size = 1024 * 1024 * 4  # 4MB chunks
            total_read = 0
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out_f.write(chunk)
                total_read += len(chunk)
                print(f"\rBaixados: {total_read / (1024*1024):.1f} MB...", end="", flush=True)
        print(f"\nDownload concluído em {time.time() - t0:.2f}s!")
    else:
        print(f"Arquivo Comex Stat já existe em {raw_csv}.")

    print("Processando e agregando fluxos de importação por NCM, Mês e UF...")
    t0 = time.time()

    # Ler em chunks usando separador ';'
    chunks = pd.read_csv(
        raw_csv,
        sep=";",
        dtype={"CO_ANO": str, "CO_MES": str, "CO_NCM": str, "SG_UF_NCM": str},
        usecols=["CO_ANO", "CO_MES", "CO_NCM", "SG_UF_NCM", "KG_LIQUIDO", "VL_FOB"],
        chunksize=250000
    )

    filtered_dfs = []
    for chunk in chunks:
        chunk["CO_NCM"] = chunk["CO_NCM"].astype(str).str.strip().str.zfill(8)
        chunk["SG_UF_NCM"] = chunk["SG_UF_NCM"].astype(str).str.strip()
        chunk["CO_MES"] = chunk["CO_MES"].astype(str).str.strip().str.zfill(2)

        # Se temos target_ncms, filtrar apenas os NCMs presentes
        if target_ncms:
            chunk = chunk[chunk["CO_NCM"].isin(target_ncms)]

        if not chunk.empty:
            agg_chunk = chunk.groupby(["CO_NCM", "CO_MES", "SG_UF_NCM"]).agg(
                qtd_operacoes=("VL_FOB", "count"),
                vl_fob_total=("VL_FOB", "sum"),
                kg_liquido_total=("KG_LIQUIDO", "sum")
            ).reset_index()
            filtered_dfs.append(agg_chunk)

    if not filtered_dfs:
        print("Nenhum registro coincidente encontrado.")
        return

    df_agg = pd.concat(filtered_dfs, ignore_index=True)
    df_final = df_agg.groupby(["CO_NCM", "CO_MES", "SG_UF_NCM"]).agg(
        qtd_operacoes=("qtd_operacoes", "sum"),
        vl_fob_total=("vl_fob_total", "sum"),
        kg_liquido_total=("kg_liquido_total", "sum")
    ).reset_index()

    df_final.to_parquet(OUTPUT_PARQUET, index=False)
    print(f"Tabela de referência Comex Stat gerada com sucesso!")
    print(f"Caminho: {OUTPUT_PARQUET} ({len(df_final):,} registros agregados NCM x Mês x UF)")
    print(f"Tempo total de processamento: {time.time() - t0:.2f}s")

if __name__ == "__main__":
    main()
