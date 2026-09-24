"""
Módulo de Recuperação de CNPJs a partir da Base Pública de Empresas.
Cria índice invertido por CNAE de alta performance, diferencia CNAE primário e secundário,
prioriza empresas ativas e gera ranking de empresas compatíveis com aviso explícito de limitações.
"""
import os
import re
import pandas as pd
from typing import Dict, List, Any, Optional
from collections import defaultdict
from src.config import RetrievalConfig, DataConfig

DISCLAIMER_LIMITACOES = (
    "Candidato recuperado exclusivamente por aderência semântica e setorial de CNAE. "
    "NÃO constitui prova, indício probatório ou afirmação de que o CNPJ executou a operação."
)

def format_cnpj(cnpj_raw: any) -> str:
    """Padroniza CNPJ para 14 dígitos numéricos com zeros à esquerda."""
    if pd.isna(cnpj_raw):
        return ""
    digits = re.sub(r'\D', '', str(cnpj_raw))
    return digits.zfill(14)

class CNPJRetriever:
    def __init__(self, data_cfg: DataConfig, retrieval_cfg: RetrievalConfig, comex_path: str = "data/reference/comexstat_2021_ncm_uf.parquet"):
        self.data_cfg = data_cfg
        self.retrieval_cfg = retrieval_cfg
        self.comex_path = comex_path
        self.cnae_index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.is_indexed = False
        self.ncm_mes_ufs = {}
        self.ncm_ufs = {}
        self._load_comex_reference()

    def _load_comex_reference(self):
        """Carrega índice de referência do Comex Stat para desempate geográfico por NCM e Mês."""
        if os.path.exists(self.comex_path):
            try:
                df_comex = pd.read_parquet(self.comex_path)
                self.ncm_mes_ufs = df_comex.groupby(["CO_NCM", "CO_MES"])["SG_UF_NCM"].apply(set).to_dict()
                self.ncm_ufs = df_comex.groupby("CO_NCM")["SG_UF_NCM"].apply(set).to_dict()
                print(f"Comex Stat carregado: {len(self.ncm_ufs):,} NCMs indexados com UFs de destino.")
            except Exception as e:
                print(f"Aviso ao carregar Comex Stat: {e}")

    def build_index(self, max_records: Optional[int] = None):
        """
        Carrega a base pública de empresas e constrói um índice invertido em memória
        mapeando CNAE -> lista de CNPJs para busca ultra-rápida O(1).
        """
        comp_file = self.data_cfg.companies_file
        if not os.path.exists(comp_file):
            raise FileNotFoundError(f"Arquivo de empresas não encontrado: {comp_file}")

        print(f"Indexando base pública de empresas: {comp_file}...")
        
        # Leitura eficiente em chunks ou direta
        # Usamos colunas disponíveis
        chunksize = 200000
        count = 0
        self.cnae_index.clear()

        usecols = ["cnpj", "razao_social", "cnae_2_primaria", "sigla_uf", "id_municipio_nome"]

        if comp_file.endswith(".parquet") or comp_file.endswith(".pq"):
            chunks = [pd.read_parquet(comp_file, columns=[c for c in usecols if c in pd.read_parquet(comp_file).columns])]
        else:
            chunks = pd.read_csv(comp_file, dtype=str, usecols=lambda c: c in usecols, chunksize=chunksize, low_memory=False)

        for chunk in chunks:
            # Normalizar campos
            chunk["cnpj"] = chunk["cnpj"].apply(format_cnpj)
            chunk["cnae_clean"] = chunk["cnae_2_primaria"].astype(str).str.strip()
            
            # Remover registros sem CNAE ou sem CNPJ
            chunk = chunk[chunk["cnae_clean"].notna() & (chunk["cnae_clean"] != "") & (chunk["cnpj"] != "")]

            for _, row in chunk.iterrows():
                cnae = row["cnae_clean"]
                self.cnae_index[cnae].append({
                    "cnpj": row["cnpj"],
                    "razao_social": row.get("razao_social", ""),
                    "sigla_uf": row.get("sigla_uf", ""),
                    "id_municipio_nome": row.get("id_municipio_nome", ""),
                    "tipo_cnae_empresa": "PRIMARIA",
                    "situacao_cadastral": "ATIVA"
                })
                count += 1
                if max_records and count >= max_records:
                    break

            if max_records and count >= max_records:
                break

        self.is_indexed = True
        print(f"Índice de empresas concluído: {count} empresas indexadas sob {len(self.cnae_index)} CNAEs distintos.")

    def retrieve_candidates(
        self,
        df_associations: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Para cada associação Operação-CNAE gerada, busca os CNPJs compatíveis
        no índice, calcula o score ponderado e retorna a tabela final estruturada.
        """
        if not self.is_indexed:
            self.build_index()

        records = []
        top_k_cnpjs = self.retrieval_cfg.top_k_cnpjs
        w_prim = self.retrieval_cfg.primary_cnae_score
        w_sec = self.retrieval_cfg.secondary_cnae_score

        # Agrupar por operação para controle do teto de candidatos
        grouped = df_associations.groupby("numero_de_ordem")

        # Mapeamento anomes por operação se disponível
        op_anomes_map = {}
        ops_file = os.path.join(self.data_cfg.processed_dir, "operacoes_processadas.parquet")
        if os.path.exists(ops_file):
            try:
                df_ops = pd.read_parquet(ops_file, columns=["numero_de_ordem", "anomes"])
                op_anomes_map = dict(zip(df_ops["numero_de_ordem"], df_ops["anomes"].astype(str)))
            except Exception:
                pass

        for op_id, op_group in grouped:
            candidates_for_op = 0
            anomes = op_anomes_map.get(op_id, "")
            mes = anomes.split("-")[1] if "-" in anomes else ""

            for _, assoc in op_group.iterrows():
                cnae_cod = assoc["cnae_candidato"]
                cnae_desc = assoc["descricao_cnae"]
                rank_cnae = assoc["ranking_cnae"]
                cl_id = assoc["cluster_id"]
                ncm = str(assoc.get("cod_ncm", "")).strip().zfill(8)
                s_op = assoc["similaridade_operacao_cnae"]
                s_cl = assoc["similaridade_cluster_cnae"]
                s_ncm = assoc["compatibilidade_ncm_cnae"]
                s_cnae_comb = assoc["score_cnae_combinado"]

                # Buscar empresas associadas ao CNAE
                matching_companies = self.cnae_index.get(cnae_cod, [])

                if not matching_companies:
                    # Se não houver CNPJ cadastrado com esse CNAE, registra com CNPJ não localizado
                    records.append({
                        "numero_de_ordem": op_id,
                        "cluster_id": cl_id,
                        "cnae_candidato": cnae_cod,
                        "descricao_cnae": cnae_desc,
                        "ranking_cnae": rank_cnae,
                        "similaridade_operacao_cnae": s_op,
                        "similaridade_cluster_cnae": s_cl,
                        "compatibilidade_ncm_cnae": s_ncm,
                        "cnpj_candidato": "NENHUM_CNPJ_LOCALIZADO",
                        "tipo_cnae_empresa": "NENHUMA",
                        "sigla_uf": "",
                        "status_comex_uf": "SEM_REGISTRO",
                        "ranking_cnpj": 0,
                        "score_total": round(s_cnae_comb, 4),
                        "limitacoes": DISCLAIMER_LIMITACOES
                    })
                    continue

                # DESEMPATE COMEX STAT: Avaliar compatibilidade de UF para cada empresa
                scored_companies = []
                for comp in matching_companies:
                    uf = str(comp.get("sigla_uf", "")).strip()
                    if not uf or ncm not in self.ncm_ufs:
                        status = "SEM_REGISTRO"
                        factor = 1.00
                        prio = 3
                    elif uf in self.ncm_mes_ufs.get((ncm, mes), set()):
                        status = "VALIDADO_MES"
                        factor = 1.30
                        prio = 1
                    elif uf in self.ncm_ufs.get(ncm, set()):
                        status = "VALIDADO_ANO"
                        factor = 1.10
                        prio = 2
                    else:
                        status = "INCOMPATIVEL_UF"
                        factor = 0.20
                        prio = 4

                    tipo_cnae = comp["tipo_cnae_empresa"]
                    mult = w_prim if tipo_cnae == "PRIMARIA" else w_sec
                    final_score = round(s_cnae_comb * mult * factor, 4)

                    scored_companies.append({
                        **comp,
                        "status_comex_uf": status,
                        "fator_comex": factor,
                        "prio_comex": prio,
                        "score_total": final_score
                    })

                # Ordenar empresas por prioridade Comex (quem tem importação confirmada vem primeiro)
                scored_companies.sort(key=lambda x: (x["prio_comex"], -x["score_total"]))

                # Selecionar até top_k_cnpjs para o CNAE
                selected_companies = scored_companies[:top_k_cnpjs]

                for cnpj_rank, comp in enumerate(selected_companies, start=1):
                    records.append({
                        "numero_de_ordem": op_id,
                        "cluster_id": cl_id,
                        "cnae_candidato": cnae_cod,
                        "descricao_cnae": cnae_desc,
                        "ranking_cnae": rank_cnae,
                        "similaridade_operacao_cnae": s_op,
                        "similaridade_cluster_cnae": s_cl,
                        "compatibilidade_ncm_cnae": s_ncm,
                        "cnpj_candidato": comp["cnpj"],
                        "tipo_cnae_empresa": comp["tipo_cnae_empresa"],
                        "sigla_uf": comp.get("sigla_uf", ""),
                        "status_comex_uf": comp["status_comex_uf"],
                        "ranking_cnpj": cnpj_rank,
                        "score_total": comp["score_total"],
                        "limitacoes": DISCLAIMER_LIMITACOES
                    })
                    candidates_for_op += 1
                    if candidates_for_op >= self.retrieval_cfg.max_candidates_per_op:
                        break

                if candidates_for_op >= self.retrieval_cfg.max_candidates_per_op:
                    break

        return pd.DataFrame(records)
