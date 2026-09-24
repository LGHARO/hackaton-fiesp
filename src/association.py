"""
Módulo de Associação entre Operações, Clusters e CNAEs oficiais.
Calcula similaridade do centróide do cluster com os CNAEs,
similaridade individual de cada operação com os CNAEs,
avalia compatibilidade estrutural NCM-CNAE (sem inventar relações não observadas)
e combina as evidências de forma heurística e transparente (NÃO probabilística).
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from sklearn.metrics.pairwise import cosine_similarity
from src.config import AssociationConfig

class CNAEAssociator:
    def __init__(self, cfg: AssociationConfig):
        self.cfg = cfg
        self.ncm_isic_map: Dict[str, str] = {}

    def build_ncm_isic_crosswalk(self, df_ncm: pd.DataFrame):
        """
        Constrói mapeamento estritamente baseado nos campos presentes no arquivo oficial NCM
        (coluna 'id_isic_classe' presente em br_bd_diretorios_mundo_nomenclatura_comum_mercosul.csv).
        ISIC Rev.4 possui correspondência direta com as classes CNAE 2.0.
        """
        if "id_isic_classe" in df_ncm.columns:
            for _, row in df_ncm.iterrows():
                ncm = str(row.get("id_ncm", "")).strip().zfill(8)
                isic = str(row.get("id_isic_classe", "")).strip()
                if isic and isic != "nan" and isic != "":
                    self.ncm_isic_map[ncm] = isic

    def check_ncm_cnae_compatibility(self, cod_ncm: str, cnae_cod_numerico: str) -> float:
        """
        Verifica se há compatibilidade verificável entre o NCM da operação e o CNAE candidato.
        Se os 4 primeiros dígitos do ISIC da NCM coincidirem com o código numérico da classe CNAE,
        retorna 1.0; se os 2 primeiros dígitos (divisão econômica) coincidirem, retorna 0.5.
        Caso não haja dados ou não coincida, retorna 0.0 de forma estrita sem inventar relações.
        """
        isic = self.ncm_isic_map.get(str(cod_ncm).strip().zfill(8), "")
        if not isic:
            return 0.0
        cnae_clean = str(cnae_cod_numerico).replace(".", "").replace("-", "").strip()
        
        # 4 dígitos (classe ISIC / CNAE)
        if len(isic) >= 4 and len(cnae_clean) >= 4 and isic[:4] == cnae_clean[:4]:
            return 1.0
        # 2 dígitos (divisão da atividade econômica)
        if len(isic) >= 2 and len(cnae_clean) >= 2 and isic[:2] == cnae_clean[:2]:
            return 0.5
        return 0.0

    def associate(
        self,
        df_ops: pd.DataFrame,
        op_embeddings: np.ndarray,
        cluster_labels: np.ndarray,
        centroids: np.ndarray,
        df_cnae: pd.DataFrame,
        cnae_embeddings: np.ndarray,
        df_ncm: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Associa cada operação e cada cluster aos CNAEs mais próximos.
        Retorna candidatos ranqueados com scores desagregados por componente.
        """
        if df_ncm is not None:
            self.build_ncm_isic_crosswalk(df_ncm)

        k_cnae = self.cfg.top_k_cnae
        cnae_codes = df_cnae["cnae_codigo"].values
        cnae_descs = df_cnae["descricao_cnae"].values
        cnae_num = df_cnae["cnae_id_numerico"].values

        # 1. Similaridade de cosseno de cada operação com todos os CNAEs
        # op_embeddings e cnae_embeddings já vêm normalizados em L2
        sim_op_cnae = np.dot(op_embeddings, cnae_embeddings.T)

        # 2. Similaridade dos centróides dos clusters com todos os CNAEs
        unique_clusters = sorted(list(set(cluster_labels)))
        cluster_idx_map = {cl: i for i, cl in enumerate(unique_clusters)}
        sim_cluster_cnae = np.dot(centroids, cnae_embeddings.T)

        results = []

        for i, row in df_ops.iterrows():
            op_id = row["numero_de_ordem"]
            cod_ncm = row["cod_ncm"]
            cl_id = int(cluster_labels[i])
            c_pos = cluster_idx_map[cl_id]

            # Scores individuais e de cluster para a operação atual
            op_sims = sim_op_cnae[i]
            cl_sims = sim_cluster_cnae[c_pos] if cl_id != -1 else np.zeros_like(op_sims)

            # Heurística de score composto:
            # Score = w_op * sim_op + w_clust * sim_clust + w_ncm * compat_ncm
            combined_scores = (
                self.cfg.weight_op_sim * op_sims +
                self.cfg.weight_cluster_sim * cl_sims
            )

            # Selecionar os top índices candidatos com base na combinação semântica
            top_candidates_idx = np.argsort(combined_scores)[::-1][:k_cnae]

            for rank, c_idx in enumerate(top_candidates_idx, start=1):
                c_code = cnae_codes[c_idx]
                c_desc = cnae_descs[c_idx]
                c_num_val = cnae_num[c_idx]

                s_op = float(op_sims[c_idx])
                s_cl = float(cl_sims[c_idx])
                s_ncm = self.check_ncm_cnae_compatibility(cod_ncm, c_num_val)

                total_score = (
                    self.cfg.weight_op_sim * s_op +
                    self.cfg.weight_cluster_sim * s_cl +
                    self.cfg.weight_ncm_compat * s_ncm
                )

                results.append({
                    "numero_de_ordem": op_id,
                    "cluster_id": cl_id,
                    "cod_ncm": cod_ncm,
                    "cnae_candidato": c_code,
                    "descricao_cnae": c_desc,
                    "ranking_cnae": rank,
                    "similaridade_operacao_cnae": round(s_op, 4),
                    "similaridade_cluster_cnae": round(s_cl, 4),
                    "compatibilidade_ncm_cnae": round(s_ncm, 4),
                    "score_cnae_combinado": round(float(total_score), 4)
                })

        return pd.DataFrame(results)
