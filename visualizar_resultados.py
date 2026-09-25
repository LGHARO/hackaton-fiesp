#!/usr/bin/env python3
"""
Módulo Standalone de Visualização dos Resultados do Pipeline.
Permite inspecionar, filtrar e auditar o arquivo `outputs/candidatos_cnpjs_finais.csv` (ou .parquet)
tanto no terminal quanto através de um Dashboard HTML interativo e autossuficiente.

Uso:
    python visualizar_resultados.py                     # Gera dashboard HTML e resumo no terminal
    python visualizar_resultados.py --op OP-1000001     # Inspeciona uma operação específica no terminal
    python visualizar_resultados.py --cluster 17        # Filtra candidatos de um cluster específico
    python visualizar_resultados.py --top 10            # Exibe as 10 operações com maiores scores médios
    python visualizar_resultados.py --open              # Abre o dashboard HTML diretamente no navegador
"""

import os
import sys
import json
import argparse
import webbrowser
import pandas as pd
import numpy as np

def load_results(csv_path: str = "outputs/candidatos_cnpjs_finais.csv") -> pd.DataFrame:
    """Carrega o arquivo de resultados (suporta CSV ou Parquet)."""
    parquet_path = csv_path.replace(".csv", ".parquet")
    if os.path.exists(parquet_path):
        df = pd.read_parquet(parquet_path)
    elif os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
    else:
        raise FileNotFoundError(f"Arquivo de resultados não encontrado em '{csv_path}' ou '{parquet_path}'.")
    return df

def enrich_with_operations(df: pd.DataFrame, ops_path: str = "data/processed/operacoes_processadas.parquet") -> pd.DataFrame:
    """Enriquece os resultados com a descrição original do produto, NCM e Ano-Mês, se disponível."""
    if os.path.exists(ops_path):
        try:
            df_ops = pd.read_parquet(ops_path, columns=["numero_de_ordem", "cod_ncm", "anomes", "descricao_do_produto", "descricao_ncm", "vmle_dolar"])
            df = df.merge(df_ops, on="numero_de_ordem", how="left")
        except Exception:
            pass
    return df

def compute_niche_metrics(df: pd.DataFrame, companies_file: str = "dados_tabela_exportacoes_importacoes.csv") -> pd.DataFrame:
    """Calcula a contagem de empresas por CNAE no Brasil, enriquece com Razão Social e UF, e calcula o Score de Especificidade."""
    df["cnpj_candidato"] = df["cnpj_candidato"].astype(str).str.strip().str.zfill(14)
    razao_dict = {}
    uf_dict = {}
    if os.path.exists(companies_file):
        try:
            df_comp = pd.read_csv(companies_file, usecols=["cnpj", "razao_social", "sigla_uf", "cnae_2_primaria"], dtype=str)
            df_comp["cnpj"] = df_comp["cnpj"].str.strip().str.zfill(14)
            cnae_counts = df_comp["cnae_2_primaria"].str.strip().value_counts().to_dict()
            df_unique = df_comp.drop_duplicates(subset=["cnpj"]).set_index("cnpj")
            razao_dict = df_unique["razao_social"].to_dict()
            uf_dict = df_unique["sigla_uf"].to_dict()
        except Exception:
            cnae_counts = df.groupby("cnae_candidato")["cnpj_candidato"].nunique().to_dict()
    else:
        cnae_counts = df.groupby("cnae_candidato")["cnpj_candidato"].nunique().to_dict()

    df["razao_social"] = df["cnpj_candidato"].map(razao_dict).fillna("N/D")
    df["sigla_uf"] = df["cnpj_candidato"].map(uf_dict).fillna("")
    df["empresas_no_cnae"] = df["cnae_candidato"].map(cnae_counts).fillna(999999).astype(int)
    # Score de Especificidade: favorece score alto em CNAEs com poucas empresas (maior probabilidade de acerto)
    df["score_especificidade"] = df["score_total"] * np.log10(100000.0 / (df["empresas_no_cnae"] + 1))
    return df

def apply_comex_stat_tiebreaker(df: pd.DataFrame, comex_path: str = "data/reference/comexstat_2021_ncm_uf.parquet") -> pd.DataFrame:
    """
    Aplica a 'Bala de Prata' do Comex Stat (MDIC):
    Cruza cada operação (NCM e mês) com os dados oficiais de comércio exterior
    para verificar se o estado da empresa candidata (UF) efetivamente registrou
    importações daquele NCM no mês ou ano de 2021.
    
    Ties (empates) entre empresas do mesmo CNAE são desempatados com bônus de confirmação ou penalização:
      - VALIDADO_MES: NCM importado pela UF da empresa no mês da compra (+30% no score).
      - VALIDADO_ANO: NCM importado pela UF da empresa em 2021 (+10% no score).
      - INCOMPATIVEL_UF: NCM nunca importado para essa UF em 2021 (-80% de penalidade).
      - SEM_REGISTRO: Sem dados suficientes para auditar (neutro).
    """
    if not os.path.exists(comex_path) or "cod_ncm" not in df.columns or "sigla_uf" not in df.columns:
        df["status_comex_uf"] = "SEM_REGISTRO"
        df["score_comex_total"] = df["score_total"]
        return df

    try:
        df_comex = pd.read_parquet(comex_path)
        ncm_mes_ufs = df_comex.groupby(["CO_NCM", "CO_MES"])["SG_UF_NCM"].apply(set).to_dict()
        ncm_ufs = df_comex.groupby("CO_NCM")["SG_UF_NCM"].apply(set).to_dict()

        ncms = df["cod_ncm"].astype(str).str.strip().str.zfill(8).values
        anomes_series = df["anomes"].astype(str).values if "anomes" in df.columns else [""] * len(df)
        ufs = df["sigla_uf"].astype(str).str.strip().values
        scores = df["score_total"].values

        status_list = []
        scores_comex = []

        for i in range(len(df)):
            ncm = ncms[i]
            uf = ufs[i]
            if not uf or ncm not in ncm_ufs:
                status_list.append("SEM_REGISTRO")
                scores_comex.append(scores[i])
                continue

            anomes = anomes_series[i]
            mes = anomes.split("-")[1] if "-" in anomes else ""

            if uf in ncm_mes_ufs.get((ncm, mes), set()):
                status_list.append("VALIDADO_MES")
                scores_comex.append(round(scores[i] * 1.30, 4))
            elif uf in ncm_ufs.get(ncm, set()):
                status_list.append("VALIDADO_ANO")
                scores_comex.append(round(scores[i] * 1.10, 4))
            else:
                status_list.append("INCOMPATIVEL_UF")
                scores_comex.append(round(scores[i] * 0.20, 4))

        df["status_comex_uf"] = status_list
        df["score_comex_total"] = scores_comex
        # Recalcular score de especificidade considerando o desempate oficial do Comex Stat
        df["score_especificidade"] = df["score_comex_total"] * np.log10(100000.0 / (df["empresas_no_cnae"] + 1))
    except Exception as e:
        print(f"Aviso ao processar Comex Stat: {e}")
        df["status_comex_uf"] = "SEM_REGISTRO"
        df["score_comex_total"] = df["score_total"]

    return df

def print_top_niche_candidates(df: pd.DataFrame, top_n: int = 50):
    """Exibe no terminal os N candidatos com maior especificidade garantindo CNPJs ÚNICOS e desempate Comex Stat."""
    # Deduplicação estrita por CNPJ para garantir empresas únicas
    top_df = df.sort_values(by="score_especificidade", ascending=False).drop_duplicates(subset=["cnpj_candidato"]).head(top_n)
    print("\n" + "="*95)
    print(f"   TOP {top_n} EMPRESAS CANDIDATAS COM DESEMPATE COMEX STAT (MDIC)")
    print("="*95)
    for i, (_, r) in enumerate(top_df.iterrows(), 1):
        prod = r.get("descricao_do_produto", "N/A")
        razao = r.get("razao_social", "N/D")
        uf = r.get("sigla_uf", "")
        uf_str = f" - {uf}" if uf else ""
        c = str(r["cnpj_candidato"]).zfill(14)
        cnpj_fmt = f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"

        comex_st = r.get("status_comex_uf", "SEM_REGISTRO")
        if comex_st == "VALIDADO_MES":
            comex_badge = f"[COMEX STAT: VALIDADO NO MÊS NA UF {uf}]"
        elif comex_st == "VALIDADO_ANO":
            comex_badge = f"[COMEX STAT: VALIDADO NO ANO 2021 NA UF {uf}]"
        elif comex_st == "INCOMPATIVEL_UF":
            comex_badge = f"[COMEX STAT: SEM REGISTRO NA UF {uf}]"
        else:
            comex_badge = "[COMEX STAT: SEM DADOS]"

        print(f"\n#{i:02d} | CNPJ: {cnpj_fmt} | {razao}{uf_str} {comex_badge}")
        print(f"    Operação: {r['numero_de_ordem']} | Cluster: #{r['cluster_id']} | Score Base: {r['score_total']:.4f} -> Comex: {r.get('score_comex_total', r['score_total']):.4f} | Esp.: {r['score_especificidade']:.2f}")
        print(f"    Produto : {prod}")
        print(f"    NCM     : {r.get('cod_ncm', 'N/A')} (Mês: {r.get('anomes', 'N/A')})")
        print(f"    CNAE    : {r['cnae_candidato']} - {r['descricao_cnae']} [APENAS {r['empresas_no_cnae']} EMPRESA(S) NO BRASIL]")
    print("\n" + "="*95 + "\n")

def print_terminal_summary(df: pd.DataFrame):
    """Exibe estatísticas gerais e distribuição dos resultados no terminal."""
    total_ops = df["numero_de_ordem"].nunique()
    total_linhas = len(df)
    total_cnpjs = df["cnpj_candidato"].nunique()
    total_cnaes = df["cnae_candidato"].nunique()
    clusters = df["cluster_id"].nunique()
    score_medio = df["score_total"].mean()
    score_max = df["score_total"].max()
    score_min = df["score_total"].min()

    print("\n" + "="*65)
    print("        RESUMO EXECUTIVO - CANDIDATOS CNPJS x CNAE")
    print("="*65)
    print(f"Total de Operações de Importação Analisadas : {total_ops:,}")
    print(f"Total de Associações Geradas               : {total_linhas:,}")
    print(f"Total de CNPJs Únicos Recuperados          : {total_cnpjs:,}")
    print(f"CNAEs Distintos Identificados              : {total_cnaes:,}")
    print(f"Clusters Formados                          : {clusters}")
    print(f"Score Total Médio                          : {score_medio:.4f} (Min: {score_min:.4f}, Max: {score_max:.4f})")
    print("="*65)

    print("\n[Top 5 CNAEs Mais Frequentes nas Operações]:")
    top_cnaes = df.groupby(["cnae_candidato", "descricao_cnae"]).size().reset_index(name="ocorrencias").sort_values("ocorrencias", ascending=False).head(5)
    for idx, r in top_cnaes.iterrows():
        print(f"  • CNAE {r['cnae_candidato']}: {r['descricao_cnae'][:50]}... ({r['ocorrencias']:,} ocorrências)")

    print("\n[Distribuição por Tipo de CNAE da Empresa]:")
    tipo_dist = df["tipo_cnae_empresa"].value_counts()
    for tipo, qtd in tipo_dist.items():
        print(f"  • {tipo}: {qtd:,} ({qtd/len(df)*100:.1f}%)")
    print("="*65 + "\n")

def inspect_operation(df: pd.DataFrame, op_id: str):
    """Exibe detalhes de uma operação específica."""
    sub = df[df["numero_de_ordem"].astype(str) == str(op_id)]
    if sub.empty:
        print(f"Nenhum resultado encontrado para a operação '{op_id}'.")
        return

    first = sub.iloc[0]
    print("\n" + "#"*70)
    print(f" DETALHES DA OPERAÇÃO: {op_id} (Cluster #{first['cluster_id']})")
    if "cod_ncm" in sub.columns and pd.notna(first.get("cod_ncm")):
        print(f" NCM Oficial : {first.get('cod_ncm')} - {first.get('descricao_ncm', '')}")
    if "descricao_do_produto" in sub.columns and pd.notna(first.get("descricao_do_produto")):
        print(f" Produto     : {first.get('descricao_do_produto')}")
    print("#"*70)

    # Agrupar por CNAE candidato
    cnaes = sub.groupby(["ranking_cnae", "cnae_candidato", "descricao_cnae", "similaridade_operacao_cnae", "similaridade_cluster_cnae", "compatibilidade_ncm_cnae"])
    for (rank, cnae_cod, cnae_desc, s_op, s_cl, s_ncm), group in cnaes:
        print(f"\n▶ [CNAE Rank #{rank}] {cnae_cod} - {cnae_desc}")
        print(f"  Similaridade Operação: {s_op:.4f} | Cluster: {s_cl:.4f} | Compat. NCM: {s_ncm:.4f}")
        print("  Top CNPJs Candidatos Recuperados:")
        for _, row in group.sort_values("ranking_cnpj").head(5).iterrows():
            print(f"    - CNPJ: {row['cnpj_candidato']} | Tipo: {row['tipo_cnae_empresa']} | Score Total: {row['score_total']:.4f}")
    print("\n" + "#"*70 + "\n")

def generate_interactive_html(df: pd.DataFrame, output_html: str = "outputs/visualizacao_interativa.html") -> str:
    """
    Gera um Dashboard HTML moderno, responsivo e interativo para navegação local.
    Permite busca instantânea, filtragem por cluster, ranking, ordenação de colunas e inspeção.
    """
    os.makedirs(os.path.dirname(output_html), exist_ok=True)

    # Selecionar colunas relevantes e converter para JSON
    cols = [
        "numero_de_ordem", "cluster_id", "cnae_candidato", "descricao_cnae",
        "ranking_cnae", "cnpj_candidato", "razao_social", "sigla_uf", "status_comex_uf", "tipo_cnae_empresa", "ranking_cnpj",
        "similaridade_operacao_cnae", "similaridade_cluster_cnae", "score_total", "score_comex_total",
        "empresas_no_cnae", "score_especificidade"
    ]
    if "descricao_do_produto" in df.columns:
        cols.append("descricao_do_produto")
    if "cod_ncm" in df.columns:
        cols.append("cod_ncm")

    # Amostrar até 2.500 linhas para garantir renderização ultra-rápida no navegador
    sample_df = df[[c for c in cols if c in df.columns]].head(2500) if len(df) > 2500 else df[[c for c in cols if c in df.columns]]
    records_json = sample_df.to_json(orient="records", force_ascii=False)

    # Top 50 Alta Especificidade: ESTRITAMENTE 50 CNPJS DISTINTOS (50 empresas diferentes)
    top50_df = df.sort_values(by="score_especificidade", ascending=False).drop_duplicates(subset=["cnpj_candidato"]).head(50)
    top50_json = top50_df[[c for c in cols if c in top50_df.columns]].to_json(orient="records", force_ascii=False)

    # Exportar arquivos dedicados do Top 50 empresas distintas do Hackathon com validação Comex Stat
    top50_cols = [
        "cnpj_candidato", "razao_social", "sigla_uf", "status_comex_uf", "numero_de_ordem",
        "cluster_id", "cod_ncm", "descricao_do_produto", "cnae_candidato",
        "descricao_cnae", "empresas_no_cnae", "tipo_cnae_empresa",
        "score_total", "score_comex_total", "score_especificidade"
    ]
    top50_export = top50_df[[c for c in top50_cols if c in top50_df.columns]].copy()
    top50_export.insert(0, "ranking", range(1, len(top50_export) + 1))
    top50_export.to_csv("outputs/top50_empresas_candidatas_hackaton.csv", index=False)
    top50_export.to_parquet("outputs/top50_empresas_candidatas_hackaton.parquet", index=False)

    total_ops = df["numero_de_ordem"].nunique()
    total_linhas = len(df)
    total_cnpjs = df["cnpj_candidato"].nunique()
    total_cnaes = df["cnae_candidato"].nunique()
    clusters = sorted(df["cluster_id"].unique().tolist())

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visualização de Candidatos CNPJs - Machine Learning</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    <style>
        body {{ background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        .kpi-card {{ background: white; border-radius: 12px; border: 1px solid #e2e8f0; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .kpi-val {{ font-size: 26px; font-weight: 700; color: #1e293b; }}
        .kpi-label {{ font-size: 13px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}
        .table-container {{ background: white; border-radius: 12px; border: 1px solid #e2e8f0; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .badge-score {{ font-size: 12px; font-weight: 600; padding: 5px 9px; border-radius: 6px; }}
        .score-high {{ background-color: #dcfce7; color: #15803d; }}
        .score-med {{ background-color: #fef9c3; color: #854d0e; }}
        .score-low {{ background-color: #f1f5f9; color: #475569; }}
        .badge-primaria {{ background-color: #e0f2fe; color: #0369a1; font-weight: 600; }}
        .badge-secundaria {{ background-color: #f3e8ff; color: #6b21a8; font-weight: 600; }}
        .disclaimer-banner {{ background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 6px; font-size: 13px; color: #92400e; margin-bottom: 20px; }}
        .table th {{ font-size: 12px; text-transform: uppercase; color: #475569; letter-spacing: 0.5px; background-color: #f8fafc; }}
        .table td {{ font-size: 13px; vertical-align: top; }}
        .product-cell {{ white-space: normal !important; word-break: break-word !important; min-width: 320px; max-width: 650px; line-height: 1.45; }}
        .cnae-desc-cell {{ white-space: normal !important; word-break: break-word !important; min-width: 220px; max-width: 450px; line-height: 1.35; }}
    </style>
</head>
<body class="py-4">
    <div class="container-fluid px-4">
        <!-- Header -->
        <div class="d-flex justify-content-between align-items-center mb-4">
            <div>
                <h3 class="fw-bold text-dark mb-1"><i class="bi bi-diagram-3-fill text-primary me-2"></i>Ranking de CNPJs Compatíveis</h3>
                <p class="text-muted mb-0">Auditoria e visualização das associações entre Operações de Importação, Clusters, CNAEs e CNPJs.</p>
            </div>
            <div>
                <span class="badge bg-secondary p-2"><i class="bi bi-filetype-csv me-1"></i>candidatos_cnpjs_finais.csv</span>
            </div>
        </div>

        <!-- Legal Disclaimer -->
        <div class="disclaimer-banner">
            <i class="bi bi-exclamation-triangle-fill me-1"></i>
            <strong>Nota Conceitual & Limitação:</strong> Os CNPJs apresentados foram recuperados por aderência de atividade econômica (CNAE). A compatibilidade semântica indica que a empresa atua no ramo do produto, <strong>NÃO</strong> constituindo prova ou afirmação de que ela realizou a importação.
        </div>

        <!-- KPIs -->
        <div class="row g-3 mb-4">
            <div class="col-md-3">
                <div class="kpi-card">
                    <div class="kpi-label">Operações Analisadas</div>
                    <div class="kpi-val">{total_ops:,}</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="kpi-card">
                    <div class="kpi-label">Candidatos Recuperados</div>
                    <div class="kpi-val">{total_linhas:,}</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="kpi-card">
                    <div class="kpi-label">CNPJs Únicos</div>
                    <div class="kpi-val">{total_cnpjs:,}</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="kpi-card">
                    <div class="kpi-label">CNAEs Distintos</div>
                    <div class="kpi-val">{total_cnaes:,}</div>
                </div>
            </div>
        </div>

        <!-- View Switcher -->
        <ul class="nav nav-pills mb-3" id="viewTabs" role="tablist">
            <li class="nav-item">
                <button class="nav-link active text-danger fw-bold" id="tab-niche" data-bs-toggle="pill" data-bs-target="#viewNiche" type="button">
                    <i class="bi bi-bullseye me-1"></i>🎯 Top 50 Empresas Únicas (50 CNPJs Distintos)
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" id="tab-ops" data-bs-toggle="pill" data-bs-target="#viewOps" type="button">
                    <i class="bi bi-collection-fill me-1"></i>Visão por Operação (1 Linha por Produto)
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" id="tab-all" data-bs-toggle="pill" data-bs-target="#viewAll" type="button">
                    <i class="bi bi-table me-1"></i>Visão Completa de Todos os Candidatos CNPJs
                </button>
            </li>
        </ul>

        <!-- Filters & Table -->
        <div class="table-container">
            <div class="row g-3 mb-3">
                <div class="col-md-5">
                    <div class="input-group">
                        <span class="input-group-text bg-white"><i class="bi bi-search"></i></span>
                        <input type="text" id="searchInput" class="form-control" placeholder="Buscar por Operação, Produto, NCM, CNPJ, Razão Social ou CNAE...">
                    </div>
                </div>
                <div class="col-md-3">
                    <select id="clusterFilter" class="form-select">
                        <option value="">Todos os Clusters</option>
                        {''.join(f'<option value="{c}">Cluster #{c}</option>' for c in clusters)}
                    </select>
                </div>
                <div class="col-md-2">
                    <select id="tipoFilter" class="form-select">
                        <option value="">CNAE Primária & Secundária</option>
                        <option value="PRIMARIA">Apenas CNAE Primária</option>
                        <option value="SECUNDARIA">Apenas CNAE Secundária</option>
                    </select>
                </div>
                <div class="col-md-2 text-end">
                    <span id="counterBadge" class="badge bg-light text-dark p-2 border">Exibindo: 0</span>
                </div>
            </div>

            <div class="tab-content">
                <!-- Visão 0: Top 50 Empresas Únicas -->
                <div class="tab-pane fade show active" id="viewNiche">
                    <div class="alert alert-danger d-flex align-items-center mb-3">
                        <i class="bi bi-bullseye fs-3 me-3 text-danger"></i>
                        <div>
                            <strong>Top 50 Empresas Únicas (50 CNPJs Distintos com Produtos Identificados):</strong> 
                            Esta visão seleciona exatamente <strong>50 empresas (CNPJs) diferentes</strong> com a maior pontuação do modelo combinada aos <strong>CNAEs mais raros do Brasil</strong> (menor número de empresas registradas na atividade econômica).
                            Cada linha apresenta uma empresa diferente, seu ramo de atuação, o produto que importou e o nível de especificidade.
                        </div>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Empresa (CNPJ & Razão Social)</th>
                                    <th>Desempate Comex Stat (UF)</th>
                                    <th>Operação</th>
                                    <th>Produto Importado</th>
                                    <th>NCM</th>
                                    <th>CNAE Estimado</th>
                                    <th>Rastreabilidade no Brasil</th>
                                    <th>Score Modelo</th>
                                    <th>Índice Especificidade</th>
                                </tr>
                            </thead>
                            <tbody id="nicheTableBody"></tbody>
                        </table>
                    </div>
                </div>

                <!-- Visão 1: Por Operação -->
                <div class="tab-pane fade" id="viewOps">
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead>
                                <tr>
                                    <th>Operação</th>
                                    <th>Cluster</th>
                                    <th>Produto Importado</th>
                                    <th>NCM</th>
                                    <th>Top 1 CNAE Estimado</th>
                                    <th>Top 1 CNPJ Candidato</th>
                                    <th>Score Top 1</th>
                                    <th>Total Candidatos</th>
                                </tr>
                            </thead>
                            <tbody id="opsTableBody"></tbody>
                        </table>
                    </div>
                </div>

                <!-- Visão 2: Completa -->
                <div class="tab-pane fade" id="viewAll">
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead>
                                <tr>
                                    <th>Operação</th>
                                    <th>Cluster</th>
                                    <th>Produto / NCM</th>
                                    <th>CNAE Candidato</th>
                                    <th>Descrição CNAE</th>
                                    <th>CNPJ Candidato</th>
                                    <th>Tipo</th>
                                    <th>Rank</th>
                                    <th>Score Total</th>
                                </tr>
                            </thead>
                            <tbody id="allTableBody"></tbody>
                        </table>
                    </div>
                </div>
            </div>
            <div class="text-center text-muted small mt-2" id="limitNote"></div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        const rawData = {records_json};
        const opsTableBody = document.getElementById("opsTableBody");
        const allTableBody = document.getElementById("allTableBody");
        const searchInput = document.getElementById("searchInput");
        const clusterFilter = document.getElementById("clusterFilter");
        const tipoFilter = document.getElementById("tipoFilter");
        const counterBadge = document.getElementById("counterBadge");
        const limitNote = document.getElementById("limitNote");

        function formatCnpj(v) {{
            if (!v || v.length !== 14) return v;
            return v.replace(/^(\\d{{2}})(\\d{{3}})(\\d{{3}})(\\d{{4}})(\\d{{2}})$/, "$1.$2.$3/$4-$5");
        }}

        function getScoreClass(score) {{
            if (score >= 0.55) return "score-high";
            if (score >= 0.40) return "score-med";
            return "score-low";
        }}

        function renderTable() {{
            const search = searchInput.value.toLowerCase().trim();
            const cluster = clusterFilter.value;
            const tipo = tipoFilter.value;

            // 1. Filtrar registros brutos
            const filtered = rawData.filter(r => {{
                if (cluster && String(r.cluster_id) !== String(cluster)) return false;
                if (tipo && r.tipo_cnae_empresa !== tipo) return false;
                if (search) {{
                    const matchOp = String(r.numero_de_ordem).toLowerCase().includes(search);
                    const matchCnpj = String(r.cnpj_candidato).toLowerCase().includes(search);
                    const matchRazao = r.razao_social ? String(r.razao_social).toLowerCase().includes(search) : false;
                    const matchCnae = String(r.cnae_candidato).toLowerCase().includes(search) || String(r.descricao_cnae).toLowerCase().includes(search);
                    const matchProd = r.descricao_do_produto ? String(r.descricao_do_produto).toLowerCase().includes(search) : false;
                    const matchNcm = r.cod_ncm ? String(r.cod_ncm).includes(search) : false;
                    if (!matchOp && !matchCnpj && !matchRazao && !matchCnae && !matchProd && !matchNcm) return false;
                }}
                return true;
            }});

            // 2. Agrupar por Operação
            const opsMap = new Map();
            for (const r of filtered) {{
                const opId = r.numero_de_ordem;
                if (!opsMap.has(opId)) {{
                    opsMap.set(opId, {{
                        numero_de_ordem: opId,
                        cluster_id: r.cluster_id,
                        descricao_do_produto: r.descricao_do_produto,
                        cod_ncm: r.cod_ncm,
                        top1_cnae: r.cnae_candidato,
                        top1_cnae_desc: r.descricao_cnae,
                        top1_cnpj: r.cnpj_candidato,
                        top1_razao: r.razao_social,
                        top1_uf: r.sigla_uf,
                        top1_score: r.score_total,
                        total_candidates: 0
                    }});
                }}
                opsMap.get(opId).total_candidates += 1;
            }}

            const uniqueOps = Array.from(opsMap.values());
            counterBadge.textContent = `Operações: ${{uniqueOps.length.toLocaleString()}} | Candidatos: ${{filtered.length.toLocaleString()}}`;

            if (uniqueOps.length > 500) {{
                limitNote.textContent = "Exibindo as primeiras 500 operações. Use a busca ou filtros para refinar.";
            }} else {{
                limitNote.textContent = "";
            }}

            // Render Visão por Operação
            let opsHtml = "";
            for (const op of uniqueOps.slice(0, 500)) {{
                const scoreClass = getScoreClass(op.top1_score);
                const prod = op.descricao_do_produto || "NÃO INFORMADO";
                const razaoTxt = op.top1_razao && op.top1_razao !== 'N/D' ? `<div class="small text-muted">${{op.top1_razao}}</div>` : '';
                opsHtml += `
                <tr>
                    <td><span class="badge bg-light text-dark border fw-bold">${{op.numero_de_ordem}}</span></td>
                    <td><span class="badge bg-secondary">#${{op.cluster_id}}</span></td>
                    <td><div class="product-cell fw-semibold text-dark">${{prod}}</div></td>
                    <td><code>${{op.cod_ncm || 'N/A'}}</code></td>
                    <td><code>${{op.top1_cnae}}</code> <div class="cnae-desc-cell text-muted">${{op.top1_cnae_desc}}</div></td>
                    <td><strong>${{formatCnpj(op.top1_cnpj)}}</strong>${{razaoTxt}}</td>
                    <td><span class="badge-score ${{scoreClass}}">${{Number(op.top1_score).toFixed(4)}}</span></td>
                    <td><span class="badge bg-primary">${{op.total_candidates}} CNPJs</span></td>
                </tr>`;
            }}
            opsTableBody.innerHTML = opsHtml;

            // Render Visão Completa Linha a Linha
            let allHtml = "";
            for (const r of filtered.slice(0, 500)) {{
                const scoreClass = getScoreClass(r.score_total);
                const tipoBadge = r.tipo_cnae_empresa === "PRIMARIA" ? "badge-primaria" : "badge-secundaria";
                const prod = r.descricao_do_produto ? 
                    `<div class="product-cell fw-semibold text-dark">${{r.descricao_do_produto}}</div>
                     <small class="text-muted">NCM: ${{r.cod_ncm || 'N/A'}}</small>` : 
                    `<span class="text-muted">N/A</span>`;
                const razaoTxt = r.razao_social && r.razao_social !== 'N/D' ? `<div class="small text-muted">${{r.razao_social}}</div>` : '';

                allHtml += `
                <tr>
                    <td><span class="badge bg-light text-dark border fw-bold">${{r.numero_de_ordem}}</span></td>
                    <td><span class="badge bg-secondary">#${{r.cluster_id}}</span></td>
                    <td>${{prod}}</td>
                    <td><code>${{r.cnae_candidato}}</code></td>
                    <td><div class="cnae-desc-cell">${{r.descricao_cnae}}</div></td>
                    <td><strong>${{formatCnpj(r.cnpj_candidato)}}</strong>${{razaoTxt}}</td>
                    <td><span class="badge ${{tipoBadge}}">${{r.tipo_cnae_empresa}}</span></td>
                    <td class="text-center">#${{r.ranking_cnpj}}</td>
                    <td><span class="badge-score ${{scoreClass}}">${{Number(r.score_total).toFixed(4)}}</span></td>
                </tr>`;
            }}
            allTableBody.innerHTML = allHtml;
        }}

        const top50Data = {top50_json};
        const nicheTableBody = document.getElementById("nicheTableBody");

        // Renderizar Top 50 Empresas Únicas
        let nicheHtml = "";
        top50Data.forEach((r, idx) => {{
            const scoreClass = getScoreClass(r.score_total);
            const prod = r.descricao_do_produto || "NÃO INFORMADO";
            const badgeEmpresa = r.empresas_no_cnae <= 5 ? "bg-danger" : (r.empresas_no_cnae <= 20 ? "bg-warning text-dark" : "bg-secondary");
            const razao = r.razao_social || "N/D";
            const uf = r.sigla_uf ? `<span class="badge bg-light text-dark border ms-1">${{r.sigla_uf}}</span>` : "";
            const tipoBadge = r.tipo_cnae_empresa === "PRIMARIA" ? "badge-primaria" : "badge-secundaria";

            let comexBadge = '<span class="badge bg-secondary">Sem Dados</span>';
            if (r.status_comex_uf === "VALIDADO_MES") {{
                comexBadge = '<span class="badge bg-success px-2 py-1"><i class="bi bi-patch-check-fill me-1"></i>Validado no Mês</span><div class="small text-success mt-1 fw-bold">NCM importado p/ ' + (r.sigla_uf || 'UF') + '</div>';
            }} else if (r.status_comex_uf === "VALIDADO_ANO") {{
                comexBadge = '<span class="badge bg-warning text-dark px-2 py-1"><i class="bi bi-check-circle me-1"></i>Validado em 2021</span><div class="small text-muted mt-1">NCM importado p/ ' + (r.sigla_uf || 'UF') + '</div>';
            }} else if (r.status_comex_uf === "INCOMPATIVEL_UF") {{
                comexBadge = '<span class="badge bg-danger px-2 py-1"><i class="bi bi-x-circle-fill me-1"></i>Incompatível</span><div class="small text-danger mt-1">0 importações p/ ' + (r.sigla_uf || 'UF') + '</div>';
            }}

            nicheHtml += `
            <tr>
                <td><span class="badge bg-dark">#${{idx + 1}}</span></td>
                <td>
                    <div class="fw-bold text-dark">${{formatCnpj(r.cnpj_candidato)}} ${{uf}}</div>
                    <div class="text-secondary small fw-medium mt-1">${{razao}}</div>
                    <div class="mt-1"><span class="badge ${{tipoBadge}}">${{r.tipo_cnae_empresa || 'PRIMARIA'}}</span></div>
                </td>
                <td>${{comexBadge}}</td>
                <td>
                    <span class="badge bg-light text-dark border fw-bold">${{r.numero_de_ordem}}</span>
                    <div class="mt-1"><span class="badge bg-secondary">Cluster #${{r.cluster_id}}</span></div>
                </td>
                <td><div class="product-cell fw-semibold text-dark">${{prod}}</div></td>
                <td><code>${{r.cod_ncm || 'N/A'}}</code></td>
                <td><code>${{r.cnae_candidato}}</code> <div class="cnae-desc-cell text-muted">${{r.descricao_cnae}}</div></td>
                <td><span class="badge ${{badgeEmpresa}} px-2 py-1">Apenas ${{r.empresas_no_cnae}} no Brasil</span></td>
                <td><span class="badge-score ${{scoreClass}}">${{Number(r.score_total).toFixed(4)}}</span></td>
                <td><span class="badge bg-danger px-2 py-1">${{Number(r.score_especificidade).toFixed(2)}}</span></td>
            </tr>`;
        }});
        nicheTableBody.innerHTML = nicheHtml;

        searchInput.addEventListener("input", renderTable);
        clusterFilter.addEventListener("change", renderTable);
        tipoFilter.addEventListener("change", renderTable);

        // Initial render
        renderTable();
    </script>
</body>
</html>
"""
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nDashboard HTML interativo gerado com sucesso!")
    print(f"Caminho do arquivo: {os.path.abspath(output_html)}")
    return output_html

def main():
    parser = argparse.ArgumentParser(
        description="Visualizador Interativo e Auditoria do arquivo candidatos_cnpjs_finais.csv"
    )
    parser.add_argument(
        "--file",
        type=str,
        default="outputs/candidatos_cnpjs_finais.csv",
        help="Caminho do arquivo de candidatos (CSV ou Parquet)."
    )
    parser.add_argument(
        "--op",
        type=str,
        default=None,
        help="Filtrar e inspecionar uma operação específica (ex: OP-1000001)."
    )
    parser.add_argument(
        "--cluster",
        type=int,
        default=None,
        help="Filtrar por ID do cluster no terminal."
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Exibir as N operações com maior média de score total."
    )
    parser.add_argument(
        "--top-especificos",
        type=int,
        default=None,
        nargs="?",
        const=50,
        help="Exibir no terminal os N candidatos com maior especificidade (score alto + CNAE com poucas empresas). Padrão: 50."
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Abre o arquivo HTML gerado diretamente no navegador padrão."
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Não gera o arquivo HTML, exibindo apenas no terminal."
    )

    args = parser.parse_args()

    # Carregar dados
    df = load_results(args.file)
    df = enrich_with_operations(df)
    df = compute_niche_metrics(df)
    df = apply_comex_stat_tiebreaker(df)

    # Exibição específica no terminal se solicitada
    if args.op:
        inspect_operation(df, args.op)
        return

    if args.cluster is not None:
        sub = df[df["cluster_id"] == args.cluster]
        print(f"\n[Exibindo resultados do Cluster #{args.cluster} ({len(sub)} candidatos)]:")
        print(sub[["numero_de_ordem", "cnae_candidato", "descricao_cnae", "cnpj_candidato", "score_total"]].head(15).to_string(index=False))
        return

    if args.top is not None:
        top_ops = df.groupby("numero_de_ordem")["score_total"].mean().reset_index().sort_values("score_total", ascending=False).head(args.top)
        print(f"\n[Top {args.top} Operações com Maior Score Médio]:")
        for _, r in top_ops.iterrows():
            print(f"  • Operação {r['numero_de_ordem']}: Score Médio = {r['score_total']:.4f}")
        return

    if args.top_especificos is not None:
        print_top_niche_candidates(df, args.top_especificos)
        return

    # Resumo geral no terminal
    print_terminal_summary(df)

    # Gerar HTML interativo
    if not args.no_html:
        html_path = generate_interactive_html(df)
        if args.open:
            webbrowser.open(f"file://{os.path.abspath(html_path)}")

if __name__ == "__main__":
    main()
